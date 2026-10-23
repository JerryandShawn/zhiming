"""Actual migration identities drive owner-local legacy withdrawal and safe rejection."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from psycopg import sql

from migration_core import migrate
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository

LEGACY_ID = "synthetic-legacy-memory"
BODY = "我喜欢合成安静书房"


def source(directory: Path, representation: str, *, inactive: bool = False) -> Path:
    directory.mkdir()
    with sqlite3.connect(directory / "web.db") as connection:
        connection.execute(
            "CREATE TABLE turns(id TEXT,session_id TEXT,message TEXT,answer TEXT,status TEXT,created_at TEXT)"
        )
        connection.execute(
            "CREATE TABLE memories(id TEXT,text TEXT,quote TEXT,category TEXT,source_turn TEXT,status TEXT)"
        )
        if representation in {"fact", "excluded"}:
            text = "不要保存。" + BODY if representation == "excluded" else BODY
            connection.execute(
                "INSERT INTO turns VALUES('turn-a','shared',?,'','complete','2026-10-17T00:00:00+00:00')", (text,)
            )
        connection.execute(
            "INSERT INTO memories VALUES(?,?,?,?,?,?)",
            (LEGACY_ID, BODY, BODY, "偏好", "turn-a", "deleted" if inactive else "active"),
        )
    return directory


def native_import(repo: PostgresRepository, directory: Path, owner: str = "alice") -> dict:
    report = migrate(directory, owner, repository=repo, apply=True)
    assert report["errors"] == [] and report["source_unchanged"] is True
    return report


def inactive(repo: PostgresRepository, directory: Path) -> dict:
    with sqlite3.connect(directory / "web.db") as connection:
        connection.execute("DELETE FROM turns")
        connection.execute("UPDATE memories SET status='deleted'")
    native_import(repo, directory)
    ledger = repo.export_privacy("alice")
    assert [(row["kind"], row["entity_id"]) for row in ledger["revocations"]] == [("legacy_memory", LEGACY_ID)]
    assert BODY not in json.dumps(ledger, ensure_ascii=False)
    return ledger


def entity(repo: PostgresRepository, owner: str, result_id: str) -> dict:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL("SELECT kind,id,status,data FROM {} WHERE owner=%s AND id=%s").format(repo.table("core_entities")),
            (owner, result_id),
        ).fetchall()
    assert len(rows) == 1
    return rows[0]


def state(repo: PostgresRepository) -> dict:
    hashes = {}
    with repo.transaction() as connection:
        tables = connection.execute(
            "SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname=%s AND relkind='r' ORDER BY relname",
            (repo.schema,),
        ).fetchall()
        for table in tables:
            hashes[table["relname"]] = connection.execute(
                sql.SQL(
                    "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),"
                    "'[]'::jsonb)::text,'UTF8')),'hex') AS value FROM {} t"
                ).format(repo.table(table["relname"])),
            ).fetchone()["value"]
    return hashes


@pytest.mark.parametrize("representation", ["legacy", "fact"])
def test_native_mapper_targets_use_actual_kind_and_original_erasure_paths(p2_repo, tmp_path, representation):
    repo = p2_repo
    directory = source(tmp_path / "native-source", representation)
    native_import(repo, directory)
    mapping = repo.legacy_mapping("alice", "memories", LEGACY_ID, "fact")
    assert mapping["kind"] == "fact" and mapping["result_id"]
    original = entity(repo, "alice", mapping["result_id"])
    assert original["kind"] == representation and original["data"]["content"] == BODY
    lineage = "fact_ids" if representation == "fact" else "source_ids"
    note = repo.put("alice", "note", "synthetic-derived-note", {"content": BODY, lineage: [original["id"]]})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(owner,kind,entity_id,chunk,model,vec,content_fp) VALUES(%s,%s,%s,0,%s,%s,%s)"
            ).format(repo.table("core_embeddings")),
            ("alice", representation, original["id"], "synthetic-local", [0.1, 0.2], "a" * 64),
        )
    ledger = inactive(repo, directory)
    assert entity(repo, "alice", original["id"])["data"]["content"] == BODY
    repo.apply_privacy("alice", ledger)
    deleted = entity(repo, "alice", original["id"])
    assert deleted["status"] == "deleted" and deleted["data"] == {}
    assert repo.get("alice", "note", note["id"], include_deleted=True)["status"] == "deleted"
    assert repo.legacy_mapping("alice", "memories", LEGACY_ID, "fact") == mapping
    with repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s AND entity_id=%s").format(
                    repo.table("core_embeddings")
                ),
                ("alice", original["id"]),
            ).fetchone()["n"]
            == 0
        )
    first = state(repo)
    repo.apply_privacy("alice", ledger)
    assert state(repo) == first


@pytest.mark.parametrize("missing", ["no_map", "excluded", "absent_entity"])
def test_native_tombstone_without_present_mapped_body_remains_a_guard(p2_repo, tmp_path, missing):
    repo = p2_repo
    directory = source(
        tmp_path / "native-source", "excluded" if missing == "excluded" else "legacy", inactive=missing == "no_map"
    )
    native_import(repo, directory)
    mapping = repo.legacy_mapping("alice", "memories", LEGACY_ID, "fact")
    if missing == "no_map":
        assert mapping is None
        ledger = repo.export_privacy("alice")
    else:
        if missing == "excluded":
            assert mapping["result_id"] is None and mapping["status"] == "excluded"
        else:
            with repo.transaction("alice") as connection:
                connection.execute(
                    sql.SQL("DELETE FROM {} WHERE owner=%s AND id=%s").format(repo.table("core_entities")),
                    ("alice", mapping["result_id"]),
                )
        ledger = inactive(repo, directory)
    before = state(repo)
    repo.apply_privacy("alice", ledger)
    assert repo.is_revoked("alice", "legacy_memory", LEGACY_ID)
    assert repo.legacy_mapping("alice", "memories", LEGACY_ID, "fact") == mapping
    assert state(repo) == before


@pytest.mark.parametrize("boundary", ["ambiguous", "archive", "foreign"])
def test_ambiguous_or_mismatched_target_rolls_back_and_foreign_owner_is_preserved(p2_repo, tmp_path, boundary):
    repo = p2_repo
    directory = source(tmp_path / "native-source", "legacy")
    native_import(repo, directory)
    mapping = repo.legacy_mapping("alice", "memories", LEGACY_ID, "fact")
    original = entity(repo, "alice", mapping["result_id"])
    ledger = inactive(repo, directory)
    if boundary == "ambiguous":
        repo.put("alice", "fact", original["id"], {"content": "SYNTHETIC_AMBIGUOUS_BODY"})
    elif boundary == "archive":
        current = repo.get("alice", "legacy", original["id"])
        repo.update(
            "alice", "legacy", original["id"], {"source": "archive:user"}, expected_revision=current["revision"]
        )
    else:
        bob_source = source(tmp_path / "bob-native-source", "legacy")
        native_import(repo, bob_source, "bob")
        bob_map = repo.legacy_mapping("bob", "memories", LEGACY_ID, "fact")
        assert bob_map["result_id"] != original["id"]
        with repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET result_id=%s WHERE owner=%s AND source='memories' AND legacy_id=%s AND kind='fact'"
                ).format(repo.table("core_legacy_map")),
                (bob_map["result_id"], "alice", LEGACY_ID),
            )
    before = state(repo)
    if boundary == "foreign":
        repo.apply_privacy("alice", ledger)
        assert entity(repo, "bob", bob_map["result_id"])["data"]["content"] == BODY
    else:
        with pytest.raises(EvidenceError, match="Legacy withdrawal target identity"):
            repo.apply_privacy("alice", ledger)
    assert state(repo) == before

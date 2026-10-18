"""Forward schema, owner isolation, latest queries, vectors and runtime grants."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.tokenize import tokenize
from mingjing_core.repositories.foundation import migration_manifest, validate_history
from mingjing_core.repositories.permissions import grant_runtime_tables
from mingjing_core.repositories.postgres import PostgresRepository


def test_migration_accepts_only_contiguous_known_verified_prefix() -> None:
    expected = migration_manifest()
    validate_history({key: value for key, value in expected.items() if key <= 4}, expected, complete=False)
    with pytest.raises(EvidenceError, match="Pending"):
        validate_history({key: value for key, value in expected.items() if key <= 4}, expected, complete=True)
    for actual in ({1: expected[1], 3: expected[3]}, dict(expected, **{}) | {8: "unknown"}, {1: "tampered"}):
        with pytest.raises(EvidenceError):
            validate_history(actual, expected, complete=False)
    with pytest.raises(EvidenceError, match="newer"):
        validate_history(expected, {key: value for key, value in expected.items() if key <= 4}, complete=True)


def test_existing_four_migrations_with_data_upgrade_atomically(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    schema = "p2_legacy_" + uuid.uuid4().hex
    try:
        with repo.transaction() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
            connection.execute("CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text)")
            for path in sorted(Path("mingjing_core/repositories/migrations").glob("000[1-4]_*.sql")):
                text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                connection.execute(text)
                connection.execute(
                    "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
                    (int(path.name[:4]), hashlib.sha256(text.encode()).hexdigest()),
                )
            connection.execute("INSERT INTO core_owners(id) VALUES('legacy')")
            connection.execute("INSERT INTO core_subjects(owner,id,label) VALUES('legacy','self','合成')")
            connection.execute(
                "INSERT INTO core_entities(owner,kind,id,subject,data) VALUES('legacy','message','old','self',%s)",
                (Jsonb({"role": "user", "content": "合成既有消息"}),),
            )
            constraint = connection.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid='core_runs'::regclass AND contype='c'"
            ).fetchone()
            assert constraint["conname"] == "core_runs_check"
        upgraded = PostgresRepository(repo.dsn, schema=schema)
        try:
            assert upgraded.verify_schema()["version"] == 7
            assert upgraded.get("legacy", "message", "old")["content"] == "合成既有消息"
            upgraded.initialize()
            assert upgraded.verify_schema()["version"] == 7
        finally:
            upgraded.close()
    finally:
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_schema_database_gap_future_and_checksum_fail_before_use(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    with repo.transaction() as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET checksum='tampered' WHERE version=3").format(repo.table("schema_migrations"))
        )
    with pytest.raises(EvidenceError, match="checksum"):
        repo.verify_schema()
    with pytest.raises(EvidenceError, match="checksum"):
        repo.initialize()


def test_list_desc_and_stable_before_take_the_latest(p2_repo: PostgresRepository) -> None:
    memory = MemoryService(p2_repo)
    values = [memory.receive("alice", content=f"合成消息{i}", source_id=f"msg-{i}") for i in range(6)]
    newest = p2_repo.list("alice", "message", order="desc", limit=2)
    assert [row["id"] for row in newest] == [values[5]["id"], values[4]["id"]]
    before = (newest[-1]["created_at"], newest[-1]["id"])
    assert p2_repo.list("alice", "message", order="desc", before=before, limit=1)[0]["id"] == values[3]["id"]
    assert p2_repo.list("alice", "message", limit=1)[0]["id"] == values[0]["id"]
    with pytest.raises(ValueError):
        p2_repo.list("alice", "message", order="DESC; DROP TABLE")


def test_search_uses_chinese_terms_and_cannot_cross_owner_subject_or_retirement(p2_repo: PostgresRepository) -> None:
    memory = MemoryService(p2_repo)
    alice = memory.receive("alice", content="我的喜用神与十神大运记录", source_id="alice")
    memory.receive("bob", content="我的喜用神与十神大运记录", source_id="bob")
    assert {"喜用神", "十神", "大运"} <= set(tokenize(alice["content"]))
    found = p2_repo.search("alice", "self", ["喜用神", "大运"], ["message"], 10)
    assert [row["id"] for row in found] == [alice["id"]]
    p2_repo.delete("alice", "message", alice["id"], expected_revision=alice["revision"])
    assert p2_repo.search("alice", "self", ["喜用神"], ["message"], 10) == []


@pytest.mark.parametrize("retirement", ["deleted", "empty"])
def test_database_trigger_deletes_only_matching_embedding(p2_repo: PostgresRepository, retirement: str) -> None:
    repo = p2_repo
    for owner in ("alice", "bob"):
        repo.put(owner, "note", "same", {"content": "合成向量原文"}, expected_revision=0)
    with repo.transaction() as connection:
        for owner in ("alice", "bob"):
            connection.execute(
                sql.SQL("INSERT INTO {} VALUES(%s,'note','same',0,'synthetic',ARRAY[1.0,0.0]::real[],'fp')").format(
                    repo.table("core_embeddings")
                ),
                (owner,),
            )
        expression = "status='deleted'" if retirement == "deleted" else "data='{{}}'"
        connection.execute(
            sql.SQL("UPDATE {} SET " + expression + " WHERE owner='alice' AND kind='note' AND id='same'").format(
                repo.table("core_entities")
            )
        )
        rows = connection.execute(sql.SQL("SELECT owner FROM {}").format(repo.table("core_embeddings"))).fetchall()
    assert [row["owner"] for row in rows] == ["bob"]


def test_new_tables_regranted_to_dml_role_and_migration_ledger_readonly(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    role_name = "p2_role_" + uuid.uuid4().hex[:20]
    role = sql.Identifier(role_name)
    with repo.transaction() as connection:
        connection.execute(sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(role))
    try:
        with repo.transaction() as connection:
            assert grant_runtime_tables(connection, role_name, repo.schema) == [
                "core_run_steps",
                "core_run_events",
                "core_embeddings",
            ]
            connection.execute(sql.SQL("SET LOCAL ROLE {}").format(role))
            for name in ("core_run_steps", "core_run_events", "core_embeddings"):
                assert (
                    connection.execute(sql.SQL("SELECT count(*) AS count FROM {}").format(repo.table(name))).fetchone()[
                        "count"
                    ]
                    == 0
                )
            assert connection.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT') AS allowed", (f"{repo.schema}.schema_migrations",)
            ).fetchone()["allowed"]
            assert not connection.execute(
                "SELECT has_table_privilege(current_user,%s,'UPDATE') AS allowed", (f"{repo.schema}.schema_migrations",)
            ).fetchone()["allowed"]
    finally:
        with repo.transaction() as connection:
            connection.execute(sql.SQL("DROP OWNED BY {}").format(role))
            connection.execute(sql.SQL("DROP ROLE {}").format(role))

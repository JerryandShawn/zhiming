"""Final candidate restore lineage, independent of the immutable b9 limitation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tools.b1_restore_proof_contracts import verify_monotone
from tools.b1_restore_replay_worker import state_hash
from tools.deploy_core import apply_withdrawals, export_withdrawals
from tools.deploy_core_withdrawals import OPERATION, marker_identity

PG_BIN = Path("C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/work/postgres/pgsql/bin")
PRIVATE = "SYNTHETIC_PRIVATE_DRAW_BODY"


def seed(repo: PostgresRepository) -> dict[str, str]:
    draws = {}
    for owner in ("alice", "bob"):
        case = MemoryService(repo).create_case(owner, "self", PRIVATE, operation_id="case-" + owner)
        draws[owner] = TarotService(repo).create_draw(
            owner, subject_id="self", case_id=case["id"], question=PRIVATE, idempotency_key="draw-" + owner
        )["draw"]["id"]
    return draws


def document(repo: PostgresRepository, owner_draws: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "core3-withdrawals-v2",
        "owners": [repo.export_privacy(owner) for owner in owner_draws],
        "tarot_requests": [],
        "deleted_draws": [{"owner": owner, "draw_id": ident} for owner, ident in owner_draws.items()],
        "delivery_receipts": [],
    }


def state(repo: PostgresRepository) -> str:
    with repo.transaction() as connection:
        return state_hash(repo, connection)


def markers(repo: PostgresRepository) -> list[dict[str, Any]]:
    with repo.connection() as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE operation=%s ORDER BY owner,request_key").format(
                repo.table("core_mutation_requests")
            ),
            (OPERATION,),
        ).fetchall()


def pg_tool(name: str, dsn: str, *arguments: str) -> None:
    binary = shutil.which(name) or str(PG_BIN / (name + ".exe"))
    assert Path(binary).is_file(), "actual local PostgreSQL client is required"
    fields = conninfo_to_dict(dsn)
    assert fields.get("host") in {"127.0.0.1", "::1", "localhost"}
    assert "test" in fields.get("dbname", "")
    env = dict(os.environ)
    for field, variable in {"host": "PGHOST", "port": "PGPORT", "user": "PGUSER", "dbname": "PGDATABASE"}.items():
        if field in fields:
            env[variable] = fields[field]
    version = subprocess.run([binary, "--version"], capture_output=True, check=False, timeout=20)
    assert version.returncode == 0 and b" 15." in version.stdout, "PostgreSQL15 clients required"
    result = subprocess.run([binary, *arguments], env=env, capture_output=True, check=False, timeout=60)
    assert result.returncode == 0, "local isolated backup/restore failed; protected diagnostic withheld"


@contextmanager
def restore_backup(repo: PostgresRepository, archive: Path):
    assert repo.schema.startswith("p2_test_") and len(repo.schema) == 40
    repo.close()
    with psycopg.connect(repo.dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(repo.schema)))
    pg_tool(
        "pg_restore",
        repo.dsn,
        "--dbname=",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-acl",
        str(archive),
    )
    restored = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        restored.verify_schema()
        yield restored
    finally:
        restored.close()


def test_nonempty_export_restore_reexport_and_second_apply_preserve_monotone_receipts(
    p2_repo: PostgresRepository,
    tmp_path: Path,
) -> None:
    draws = seed(p2_repo)
    archive = tmp_path / "synthetic-before-deletion.dump"
    pg_tool(
        "pg_dump",
        p2_repo.dsn,
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--schema=" + p2_repo.schema,
        "--file=" + str(archive),
    )
    p2_repo.mutation_request(
        "alice",
        "tarot-delete:" + draws["alice"],
        "source-http-delete",
        {},
        lambda: TarotService(p2_repo).delete("alice", draws["alice"]),
    )
    latest = export_withdrawals(p2_repo)
    assert latest["deleted_draws"] == [{"owner": "alice", "draw_id": draws["alice"]}]
    assert PRIVATE not in json.dumps(latest)
    with restore_backup(p2_repo, archive) as restored:
        first = apply_withdrawals(restored, latest)
        assert first["deleted_draws"] == first["draw_tombstones_added"] == 1
        assert first["model_calls"] == first["external_sends"] == 0
        exported = export_withdrawals(restored)
        verify_monotone(latest, exported)
        assert exported["deleted_draws"] == latest["deleted_draws"]
        assert TarotService(restored).get("bob", draws["bob"])["question"] == PRIVATE
        before, rows = state(restored), markers(restored)
        second = apply_withdrawals(restored, exported)
        assert second["deleted_draws"] == second["draw_tombstones_added"] == 0
        assert state(restored) == before and markers(restored) == rows
        assert export_withdrawals(restored) == exported
        assert len(rows) == 1 and set(rows[0]["receipt"]) == {"deleted", "deleted_ids", "kind"}
        assert PRIVATE not in json.dumps(rows, default=str)


def test_normal_and_restore_receipts_export_one_canonical_pair(p2_repo: PostgresRepository) -> None:
    draws = seed(p2_repo)
    p2_repo.mutation_request(
        "alice",
        "tarot-delete:" + draws["alice"],
        "source-delete",
        {},
        lambda: TarotService(p2_repo).delete("alice", draws["alice"]),
    )
    original = export_withdrawals(p2_repo)
    apply_withdrawals(p2_repo, original)
    exported = export_withdrawals(p2_repo)
    assert exported["deleted_draws"] == original["deleted_draws"]
    with p2_repo.connection() as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {} WHERE owner='alice' AND operation LIKE 'tarot-delete:%%'").format(
                    p2_repo.table("core_mutation_requests")
                )
            ).fetchone()["n"]
            == 2
        )


@pytest.mark.parametrize("deleted", [False, True])
def test_foreign_owner_draw_or_prior_tombstone_cannot_be_rebound(p2_repo: PostgresRepository, deleted: bool) -> None:
    draws = seed(p2_repo)
    if deleted:
        p2_repo.mutation_request(
            "bob",
            "tarot-delete:" + draws["bob"],
            "bob-delete",
            {},
            lambda: TarotService(p2_repo).delete("bob", draws["bob"]),
        )
    wrong = document(p2_repo, {"alice": draws["bob"]})
    before = state(p2_repo)
    with pytest.raises(ValueError, match="different owner"):
        apply_withdrawals(p2_repo, wrong)
    assert state(p2_repo) == before and markers(p2_repo) == []


@pytest.mark.parametrize("tampered", ["fingerprint", "receipt"])
def test_tampered_second_owner_marker_rolls_back_first_owners_deletion(
    p2_repo: PostgresRepository,
    tampered: str,
) -> None:
    draws = seed(p2_repo)
    key, payload, receipt = marker_identity("bob", draws["bob"])
    digest = fingerprint(payload)
    if tampered == "fingerprint":
        digest = "0" * 64
    else:
        receipt = {**receipt, "deleted_ids": ["different-synthetic-id"]}
    with p2_repo.transaction("bob") as connection:
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,operation,request_key,fingerprint,receipt) VALUES(%s,%s,%s,%s,%s)").format(
                p2_repo.table("core_mutation_requests")
            ),
            ("bob", OPERATION, key, digest, Jsonb(receipt)),
        )
    before, prior = state(p2_repo), markers(p2_repo)
    with pytest.raises((EvidenceError, ValueError)):
        apply_withdrawals(p2_repo, document(p2_repo, draws))
    assert state(p2_repo) == before and markers(p2_repo) == prior
    assert all(TarotService(p2_repo).get(owner, ident)["question"] == PRIVATE for owner, ident in draws.items())


def test_already_missing_draw_still_has_one_stable_owner_bound_marker(p2_repo: PostgresRepository) -> None:
    seed(p2_repo)
    missing = "a" * 32
    latest = document(p2_repo, {"alice": missing})
    assert apply_withdrawals(p2_repo, latest)["draw_tombstones_added"] == 1
    snapshot = state(p2_repo)
    assert apply_withdrawals(p2_repo, latest)["draw_tombstones_added"] == 0
    assert state(p2_repo) == snapshot
    assert export_withdrawals(p2_repo)["deleted_draws"] == [{"owner": "alice", "draw_id": missing}]

"""New synthetic databases only; no reuse of application databases or production data."""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.b1_restore_proof_contracts import OWNER_ENV, WRITER_ENV, ProofRequest
from tools.b1_restore_proof_pg import state_hash
from tools.b1_restore_replay_contracts import file_hash, verify_candidate
from tools.core_incremental_contracts import (
    EXPECTED_MANIFEST,
    MIGRATIONS,
    PREVIOUS,
    STAGE_UNITS,
    TARGET,
)

ROOT = Path(__file__).resolve().parents[3]
PG_BIN = Path("C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/work/postgres/pgsql/bin")
SUPPORT = runpy.run_path(str(ROOT / "tests/test_b1_restore_replay_support.py"))


def pinned_candidate() -> Path:
    configured = os.environ.get("B1_PROOF_TEST_CANDIDATE_SOURCE")
    if configured:
        source = Path(configured)
        if not source.is_absolute():
            raise RuntimeError("Explicit B1 test candidate must be absolute")
    else:
        try:
            source = SUPPORT["materialize"]()
        except (OSError, subprocess.CalledProcessError):
            raise RuntimeError(
                "Requires verified B1_PROOF_TEST_CANDIDATE_SOURCE or local pinned b9 Git history"
            ) from None
    verify_candidate(source)
    return source.resolve()


def pg_tool(name: str) -> Path:
    if name not in {"pg_dump", "pg_restore"}:
        raise RuntimeError("Only PG15 dump/restore test tools are allowed")
    directory = Path(os.environ.get("B1_PROOF_TEST_PG_BIN", str(PG_BIN)))
    path = directory / (name + (".exe" if os.name == "nt" else ""))
    if not directory.is_absolute() or not path.is_file():
        raise RuntimeError("Explicit absolute B1_PROOF_TEST_PG_BIN with existing PG15 tools is required")
    env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result = subprocess.run([str(path), "--version"], env=env, capture_output=True, check=False, timeout=10)
    if result.returncode or not re.search(rb"PostgreSQL\) 15\.", result.stdout):
        raise RuntimeError("B1 proof test PostgreSQL tools must be version 15")
    return path


def write(path: Path, value: dict[str, Any]) -> Path:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)
    return path


def request_document() -> dict[str, Any]:
    return {
        "schema": "b1-incremental-request-v1",
        "operation_id": "b1-proof-synthetic",
        "scope": "stage",
        "hostname": "synthetic-local",
        "target": TARGET,
        "previous": PREVIOUS,
        "manifest_sha256": EXPECTED_MANIFEST,
        "controller_sha256": "a" * 64,
        "owners": ["primary"],
        "minimum_free_bytes": 8 * 1024**3,
        "unit_sha256": dict.fromkeys(STAGE_UNITS, "absent"),
    }


def empty_document() -> dict[str, Any]:
    return {
        "schema": "core3-withdrawals-v2",
        "owners": [
            {"schema_version": "core3.0", "owner_user_id": owner, "revocations": []}
            for owner in ("primary", "secondary")
        ],
        "tarot_requests": [],
        "deleted_draws": [],
        "delivery_receipts": [],
    }


@dataclass
class Fixture:
    request: ProofRequest
    source_dsn: str
    owner_dsn: str
    writer_dsn: str
    directory: Path

    def script(self, body: str, **value: Any) -> dict[str, Any]:
        return SUPPORT["candidate"](
            self.request.candidate_source, body, self.source_dsn, dict(schema="mingjing_core", **value)
        )

    def arguments(self) -> list[str]:
        result = []
        for key, value in asdict(self.request).items():
            if key == "local_drill":
                continue
            result.extend(["--" + key.replace("_", "-"), str(value)])
        return result + ["--local-drill"]


@pytest.fixture
def proof_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Fixture]:
    configured = os.environ.get("B1_PROOF_TEST_ADMIN_DSN")
    if not configured:
        pytest.skip("requires explicit disposable loopback PG15 administration DSN")
    fields = conninfo_to_dict(configured)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {"55480", "55481"}
    pg_tool("pg_dump")
    pg_tool("pg_restore")
    pinned_candidate()
    ident = uuid.uuid4().hex
    target, source = "b1_restore_proof_" + ident, "b1_restore_source_" + ident
    roles = [target + "_" + role for role in ("owner", "writer")]
    created: list[str] = []
    with psycopg.connect(configured, autocommit=True) as admin:
        assert 150000 <= admin.info.server_version < 160000
        for role in roles:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                    sql.Identifier(role)
                )
            )
        for database in (source, target):
            admin.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(roles[0]))
            )
            created.append(database)
    try:
        value = make_fixture(tmp_path, configured, target, source)
        monkeypatch.setenv(OWNER_ENV, value.owner_dsn)
        monkeypatch.setenv(WRITER_ENV, value.writer_dsn)
        yield value
    finally:
        # This fixture removes only the two exact random databases it created.
        with psycopg.connect(configured, autocommit=True) as admin:
            for database in created:
                assert database in {source, target} and database.endswith(ident)
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            for role in roles:
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def make_fixture(
    directory: Path, configured: str, target: str, source: str, *, pg_restore: Path | None = None
) -> Fixture:
    source_dsn = make_conninfo(configured, dbname=source, user=target + "_owner")
    pg_restore = pg_restore if pg_restore is not None else pg_tool("pg_restore")
    value = {
        "request": write(directory / "request.json", request_document()),
        "backup": directory / "backup.json",
        "dump": directory / "before.dump",
        "backup_ledger": write(directory / "backup-ledger.json", empty_document()),
        "ledger": write(directory / "latest-ledger.json", empty_document()),
        "ledger_sha256": file_hash(directory / "latest-ledger.json"),
        "database": target,
        "candidate_source": pinned_candidate(),
        "candidate_python": Path(sys.executable),
        "pg_restore": pg_restore,
        "pg_restore_sha256": file_hash(pg_restore),
        "local_drill": True,
    }
    request = ProofRequest(**value)
    return Fixture(
        request,
        source_dsn,
        make_conninfo(configured, dbname=target, user=target + "_owner"),
        make_conninfo(configured, dbname=target, user=target + "_writer"),
        directory,
    )


def initialize4(value: Fixture) -> None:
    with psycopg.connect(value.source_dsn) as conn:
        conn.execute("CREATE SCHEMA mingjing_core AUTHORIZATION current_user")
        conn.execute("SET search_path TO mingjing_core")
        conn.execute(
            "CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text,"
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        files = sorted((value.request.candidate_source / "mingjing_core/repositories/migrations").glob("*.sql"))
        for path in files[:4]:
            version = int(path.name[:4])
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)", (version, MIGRATIONS[str(version)])
            )


def backup(value: Fixture) -> None:
    document = value.script(
        "from mingjing_core.repositories.postgres import PostgresRepository\n"
        "from tools.deploy_core import export_withdrawals\n"
        "repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'],initialize=False)\n"
        "print(json.dumps(export_withdrawals(repo),default=str));repo.close()"
    )
    write(value.request.backup_ledger, document)
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    for name, key in (("host", "PGHOST"), ("port", "PGPORT"), ("user", "PGUSER"), ("dbname", "PGDATABASE")):
        environment[key] = conninfo_to_dict(value.source_dsn)[name]
    result = subprocess.run(
        [str(pg_tool("pg_dump")), "--format=custom", "--no-owner", "--no-acl", "--file=" + str(value.request.dump)],
        env=environment,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, "synthetic backup failed"
    value.request.dump.chmod(0o600)
    from psycopg.rows import dict_row

    with psycopg.connect(value.source_dsn, row_factory=dict_row) as conn:
        source_hash = state_hash(conn)
    write(
        value.request.backup,
        {
            "schema": "b1-quiesced-backup-v1",
            "operation_id": "b1-proof-synthetic",
            "database": "zhiming_core_stage",
            "source_state_sha256": source_hash,
            "target": TARGET,
            "manifest_sha256": EXPECTED_MANIFEST,
            "mode": "0600",
            "body_free_withdrawals": True,
            "dump_sha256": hashlib.sha256(value.request.dump.read_bytes()).hexdigest(),
            "withdrawals_sha256": file_hash(value.request.backup_ledger),
        },
    )

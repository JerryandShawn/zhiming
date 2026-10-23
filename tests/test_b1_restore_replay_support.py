"""Private immutable B1 materialization and a dedicated real PG restore database."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.b1_restore_replay_contracts import (
    DATABASE,
    EXPECTED_MANIFEST,
    TARGET,
    RestoreRequest,
)

ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable).resolve()
PG_BIN = Path("C:/Users/Administrator/Documents/Codex/2026-10-11/p-jerrymeng-asia-1-14-59/work/postgres/pgsql/bin")


def materialize() -> Path:
    destination = ROOT / "private/b1-stage-replay-20261021/candidate"
    if (destination / "__release_manifest__.json").exists():
        return destination
    require_empty = not destination.exists() or not list(destination.iterdir())
    if not require_empty:
        raise RuntimeError("B1 private candidate destination must be empty")
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "-z", TARGET],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    entries = []
    for record in filter(None, listing.split(b"\0")):
        metadata, name = record.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        assert kind == "blob" and mode in {"100644", "100755"}
        entries.append((name.decode("utf-8"), mode, blob))
    content = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=ROOT,
        input=("\n".join(blob for _, _, blob in entries) + "\n").encode(),
        capture_output=True,
        check=True,
    ).stdout
    files, position = {}, 0
    for name, mode, blob in entries:
        end = content.index(b"\n", position)
        ident, kind, length = content[position:end].decode().split()
        data = content[end + 1 : end + 1 + int(length)]
        position = end + int(length) + 2
        assert ident == blob and kind == "blob"
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == blob
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "git_blob_sha1": blob,
            "mode": int(mode, 8) & 0o777,
        }
    manifest = json.dumps(
        {"schema": "core3-release-v1", "commit": TARGET, "files": files},
        sort_keys=True,
        ensure_ascii=False,
    ).encode()
    assert hashlib.sha256(manifest).hexdigest() == EXPECTED_MANIFEST
    (destination / "__release_manifest__.json").write_bytes(manifest)
    return destination


def candidate(source: Path, body: str, dsn: str, payload: dict[str, Any]) -> dict[str, Any]:
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    environment.update(B1_FIXTURE_DSN=dsn, LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    code = f"import sys,json,os\nsys.path.insert(0,{str(source)!r})\nvalue=json.load(sys.stdin)\n" + body
    output = subprocess.run(
        [str(PYTHON), "-I", "-B", "-c", code],
        input=json.dumps(payload),
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    if output.returncode:
        raise RuntimeError("Synthetic candidate fixture failed: " + output.stderr[-1600:])
    return json.loads(output.stdout)


@dataclass
class ReplayDatabase:
    dsn: str
    source: Path
    schema: str
    directory: Path

    def script(self, body: str, **payload: Any) -> dict[str, Any]:
        return candidate(self.source, body, self.dsn, dict(schema=self.schema, **payload))

    def request(self, document: dict[str, Any], **changes: Any) -> RestoreRequest:
        path = self.directory / (uuid.uuid4().hex + ".json")
        path.write_text(json.dumps(document), encoding="utf-8")
        path.chmod(0o600)
        fields = {
            "operation_id": "b1-replay-" + uuid.uuid4().hex,
            "scope": "stage",
            "database": DATABASE,
            "schema": self.schema,
            "candidate_source": self.source,
            "candidate_python": PYTHON,
            "ledger": path,
            "ledger_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "local_drill": True,
        }
        return RestoreRequest(**dict(fields, **changes))

    def pg(self, tool: str, *arguments: str) -> None:
        fields = conninfo_to_dict(self.dsn)
        environment = {
            key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ
        }
        for name, key in (
            ("host", "PGHOST"),
            ("port", "PGPORT"),
            ("dbname", "PGDATABASE"),
            ("user", "PGUSER"),
        ):
            environment[key] = fields[name]
        command = PG_BIN / (tool + (".exe" if os.name == "nt" else ""))
        result = subprocess.run([str(command), *arguments], env=environment, capture_output=True, timeout=60)
        assert result.returncode == 0, "Synthetic PostgreSQL backup/restore failed"


@pytest.fixture(scope="session")
def b1_restore_dsn() -> str:
    configured = os.environ.get("B1_REPLAY_TEST_ADMIN_DSN")
    if not configured:
        pytest.skip("requires explicit disposable loopback PG15 administration DSN")
    fields = conninfo_to_dict(configured)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {
        "55480",
        "55481",
    }
    with psycopg.connect(configured, autocommit=True) as connection:
        assert 150000 <= connection.info.server_version < 160000
        for suffix in ("owner", "writer"):
            role = DATABASE + "_" + suffix
            if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone():
                connection.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(role))
                )
        found = connection.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=%s",
            (DATABASE,),
        ).fetchone()
        if not found:
            connection.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(DATABASE), sql.Identifier(DATABASE + "_owner")
                )
            )
        else:
            assert found[0] == DATABASE + "_owner", "Refuse an unrelated existing database"
    return make_conninfo(configured, dbname=DATABASE, user=DATABASE + "_owner")


@pytest.fixture
def replay_db(b1_restore_dsn: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ReplayDatabase]:
    for name in list(os.environ):
        if any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD")):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("B1_RESTORE_OWNER_DSN", b1_restore_dsn)
    schema = "b1_replay_" + uuid.uuid4().hex
    value = ReplayDatabase(b1_restore_dsn, materialize(), schema, tmp_path)
    yield value
    assert schema.startswith("b1_replay_") and len(schema) == 42
    with psycopg.connect(b1_restore_dsn) as connection:
        if connection.execute("SELECT to_regclass(%s)", (schema + ".core_runs",)).fetchone()[0]:
            runs = connection.execute(
                sql.SQL("SELECT id,retry_epoch FROM {}.core_runs").format(sql.Identifier(schema))
            ).fetchall()
            threads = [run[0] + ":e" + str(epoch) for run in runs for epoch in range(run[1] + 1)]
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                if connection.execute("SELECT to_regclass(%s)", (table,)).fetchone()[0]:
                    connection.execute(
                        sql.SQL("DELETE FROM {} WHERE thread_id=ANY(%s)").format(sql.Identifier(table)), (threads,)
                    )
        connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))

"""Only this fixture's fresh random database and non-elevated roles are disposable."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from b1_restore_proof_support import pinned_candidate
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.b1_bootstrap_replay_fixture import DSN_ENV, SeedRequest
from tools.b1_linux_drill_sql import fixture_sql
from tools.core_incremental_contracts import MIGRATIONS


@dataclass(frozen=True)
class SeedDatabase:
    dsn: str
    source: Path

    def request(self, phase: str = "seed") -> SeedRequest:
        return SeedRequest("b1-seed-synthetic-operation", phase, self.source, Path(sys.executable).resolve())

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)


def initialize4(value: SeedDatabase) -> None:
    with value.connect() as conn:
        conn.execute("CREATE SCHEMA mingjing_core AUTHORIZATION current_user")
        conn.execute("SET search_path TO mingjing_core")
        conn.execute(
            "CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text,"
            "applied_at timestamptz NOT NULL DEFAULT now())"
        )
        paths = sorted((value.source / "mingjing_core/repositories/migrations").glob("*.sql"))
        for path in paths[:4]:
            version = int(path.name[:4])
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)", (version, MIGRATIONS[str(version)])
            )
    with value.connect() as conn:
        conn.execute(fixture_sql())


@pytest.fixture
def seed_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[SeedDatabase]:
    configured = os.environ.get("B1_BOOTSTRAP_TEST_ADMIN_DSN")
    if not configured:
        pytest.skip("requires explicit disposable loopback PG15 administration DSN")
    fields = conninfo_to_dict(configured)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {"55480", "55481"}
    for key in list(os.environ):
        if key.startswith("PG") or any(part in key.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
            monkeypatch.delenv(key, raising=False)
    database = "b1_application_" + uuid.uuid4().hex
    roles = [database + "_" + suffix for suffix in ("owner", "writer")]
    source = pinned_candidate()
    with psycopg.connect(configured, autocommit=True) as admin:
        assert 150000 <= admin.info.server_version < 160000
        for role in roles:
            admin.execute(
                sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS").format(
                    sql.Identifier(role)
                )
            )
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(roles[0])))
    try:
        value = SeedDatabase(make_conninfo(configured, dbname=database, user=roles[0]), source)
        initialize4(value)
        monkeypatch.setenv(DSN_ENV, value.dsn)
        yield value
    finally:
        # Never enumerate or remove pre-existing databases, schemas, volumes, or roles.
        assert database.startswith("b1_application_") and len(database) == 47
        with psycopg.connect(configured, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
            for role in reversed(roles):
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))

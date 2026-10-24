"""Forward-only schema eight and separately downgraded central runtime role."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardConfigurationError
from mingjing_core.repositories.foundation import migration_manifest, validate_history
from mingjing_core.repositories.permissions import grant_runtime_tables
from mingjing_core.repositories.postgres import PostgresRepository

from .test_quota_guard_batches_pg import begin, evaluated
from .test_quota_guard_pg import configure_central, post


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def seed_seven(repo: PostgresRepository, schema: str) -> None:
    with repo.transaction() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
        connection.execute("CREATE TABLE schema_migrations(version integer PRIMARY KEY,checksum text)")
        for path in sorted(Path("mingjing_core/repositories/migrations").glob("000[1-7]_*.sql")):
            text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            connection.execute(text)
            connection.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
                (int(path.name[:4]), hashlib.sha256(text.encode()).hexdigest()),
            )
        connection.execute("INSERT INTO core_owners(id) VALUES('preserved-owner')")


def test_seven_to_eight_is_forward_only_idempotent_and_preserves_data(p2_repo: PostgresRepository) -> None:
    schema = "p2_quota_upgrade_" + uuid.uuid4().hex
    seed_seven(p2_repo, schema)
    try:
        upgraded = PostgresRepository(p2_repo.dsn, schema=schema)
        try:
            assert upgraded.verify_schema()["version"] == 8
            with upgraded.transaction() as connection:
                row = connection.execute(
                    sql.SQL("SELECT id FROM {} WHERE id='preserved-owner'").format(upgraded.table("core_owners"))
                ).fetchone()
                assert row["id"] == "preserved-owner"
            upgraded.initialize()
            assert upgraded.verify_schema()["version"] == 8
            expected = migration_manifest()
            assert sorted(expected) == list(range(1, 9))
            with pytest.raises(EvidenceError, match="newer"):
                validate_history(expected, {key: value for key, value in expected.items() if key <= 7}, complete=True)
        finally:
            upgraded.close()
    finally:
        with p2_repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def assert_denied(repo: PostgresRepository, role: str, statement: sql.Composable, params: Any = None) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege), repo.transaction() as connection:
        connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
        connection.execute(statement, params)


def test_dml_role_can_reserve_finish_stop_but_cannot_erase_budget_or_provision_account(
    p2_repo: PostgresRepository, central: dict[str, Any]
) -> None:
    role = "quota_runtime_" + uuid.uuid4().hex[:20]
    with p2_repo.transaction() as connection:
        connection.execute(
            sql.SQL("CREATE ROLE {} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE").format(sql.Identifier(role))
        )
    try:
        with p2_repo.transaction() as connection:
            grant_runtime_tables(connection, role, p2_repo.schema)
        runtime = dict(central, central_dsn=make_conninfo(central["central_dsn"], options=f"-c role={role}"))
        guard = QuotaGuard(**runtime)
        assert post(guard, "runtime-post") == [1]
        begin(guard)
        assert evaluated(guard, "runtime-eval") == [1]
        guard.finish_batch("batch-1", "manual-start-1")
        guard.record_stop("access_terminated")
        assert QuotaGuard(**runtime).status()["stop_kind"] == "access_terminated"
        check_runtime_restrictions(p2_repo, role)
    finally:
        with p2_repo.transaction() as connection:
            connection.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
            connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def check_runtime_restrictions(repo: PostgresRepository, role: str) -> None:
    for name in ("core_model_usage", "core_model_accounts", "core_model_batches", "core_model_authorizations"):
        assert_denied(repo, role, sql.SQL("DELETE FROM {}").format(repo.table(name)))
    assert_denied(
        repo,
        role,
        sql.SQL("INSERT INTO {}(account_id,ledger_identity,location_id) VALUES(%s,%s,%s)").format(
            repo.table("core_model_accounts")
        ),
        ("invented", str(uuid.uuid4()), "0" * 64),
    )
    assert_denied(
        repo, role, sql.SQL("UPDATE {} SET expires_at=expires_at").format(repo.table("core_model_authorizations"))
    )
    assert_denied(repo, role, sql.SQL("UPDATE {} SET checksum='changed'").format(repo.table("schema_migrations")))
    assert_denied(repo, role, sql.SQL("CREATE TABLE {}(id integer)").format(repo.table("forbidden_ddl")))


def test_cloned_account_row_in_business_schema_does_not_pass_central_location_identity(
    p2_repo: PostgresRepository, central: dict[str, Any]
) -> None:
    schema = "p2_quota_clone_" + uuid.uuid4().hex
    try:
        with p2_repo.transaction() as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            target = sql.Identifier(schema, "core_model_accounts")
            connection.execute(
                sql.SQL("CREATE TABLE {} (LIKE {} INCLUDING ALL)").format(target, p2_repo.table("core_model_accounts"))
            )
            connection.execute(
                sql.SQL("INSERT INTO {} SELECT * FROM {}").format(target, p2_repo.table("core_model_accounts"))
            )
        with pytest.raises(GuardConfigurationError):
            QuotaGuard(**dict(central, central_schema=schema))
        assert QuotaGuard(**central).status()["window"]["total"] == 0
    finally:
        with p2_repo.transaction() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

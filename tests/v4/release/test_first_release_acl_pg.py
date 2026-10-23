"""Actual PG15 correct 0008 minimal grants pass; stronger privileges fail without repairs."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from first_release_support import packed_source
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from mingjing_core.repositories.permissions import grant_runtime_tables
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.b1_restore_proof_worker import grant_checkpoints
from tools.first_release_acl import verify_database_acl
from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected


@dataclass
class Database:
    contract: RestoreContract
    pin: ReleasePin
    admin: str
    owner: str
    writer: str

    def verify(self) -> dict[str, Any]:
        return verify_database_acl(
            self.contract,
            self.pin,
            environment={
                "FIRST_RELEASE_OWNER_DSN": self.owner,
                "FIRST_RELEASE_WRITER_DSN": self.writer,
            },
        )

    @contextmanager
    def changed(self, grant: str, revoke: str, *, admin: bool = False):
        with psycopg.connect(self.admin if admin else self.owner, autocommit=True) as connection:
            connection.execute(
                sql.SQL(grant).format(
                    writer=sql.Identifier(self.contract.database + "_writer"),
                    owner=sql.Identifier(self.contract.database + "_owner"),
                    database=sql.Identifier(self.contract.database),
                )
            )
            try:
                yield
            finally:
                connection.execute(
                    sql.SQL(revoke).format(
                        writer=sql.Identifier(self.contract.database + "_writer"),
                        owner=sql.Identifier(self.contract.database + "_owner"),
                        database=sql.Identifier(self.contract.database),
                    )
                )

    @contextmanager
    def default_search_path(self, *roles: str):
        assert roles and set(roles) <= {"owner", "writer"}
        with psycopg.connect(self.admin, autocommit=True) as connection:
            try:
                for role in roles:
                    connection.execute(
                        sql.SQL("ALTER ROLE {} SET search_path TO acl_spoof,pg_catalog").format(
                            sql.Identifier(self.contract.database + "_" + role)
                        )
                    )
                yield
            finally:
                for role in roles:
                    connection.execute(
                        sql.SQL("ALTER ROLE {} RESET search_path").format(
                            sql.Identifier(self.contract.database + "_" + role)
                        )
                    )


def initialize(owner: str, writer: str) -> None:
    repo = PostgresRepository(owner)
    try:
        LangGraphRuntime(repo)
        with repo.transaction() as connection:
            grant_runtime_tables(connection, writer)
            grant_checkpoints(connection, writer)
    finally:
        repo.close()


@pytest.fixture(scope="module")
def database(tmp_path_factory):
    admin_dsn = os.environ.get("CORE_TEST_DSN", "")
    assert admin_dsn, "explicit disposable local PG15 admin DSN required"
    fields = conninfo_to_dict(admin_dsn)
    assert fields.get("host") in {"127.0.0.1", "::1"} and fields.get("port") in {"55480", "55481"}
    assert "test" in fields.get("dbname", "")
    pin, contract = packed_source(tmp_path_factory.mktemp("first-release-acl"))
    name = contract.database
    roles = [name + suffix for suffix in ("_owner", "_writer")]
    created_roles, created_db = [], False
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        assert 150000 <= admin.info.server_version < 160000
        try:
            for role in roles:
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(role))
                )
                created_roles.append(role)
            admin.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(roles[0])))
            created_db = True
            owner = make_conninfo(admin_dsn, dbname=name, user=roles[0])
            writer = make_conninfo(admin_dsn, dbname=name, user=roles[1])
            initialize(owner, roles[1])
            yield Database(contract, pin, admin_dsn, owner, writer)
        finally:
            assert name.startswith("fr_restore_") and len(name) == 43
            if created_db:
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            for role in reversed(created_roles):
                assert role in roles
                admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))


def test_correct_quota_acl_and_real_checkpoint_schema_are_read_only(database):
    with psycopg.connect(database.owner) as connection:
        before = connection.execute(
            "SELECT oid,relacl FROM pg_class WHERE "
            "relnamespace IN ('mingjing_core'::regnamespace,'public'::regnamespace) "
            "ORDER BY oid"
        ).fetchall()
    result = database.verify()
    assert result["quota_tables_checked"] == 4 and result["tables_checked"] >= 9
    assert result["sequences_checked"] >= 1 and result["database_connections"] == 2
    assert result["read_only"] is True and result["mutations"] == 0
    assert result["linux_attestation"] is result["native_restore_completed"] is result["publication"] is False
    with psycopg.connect(database.writer) as connection:
        assert connection.execute(
            "SELECT has_table_privilege(current_user,'mingjing_core.core_model_accounts','DELETE')"
        ).fetchone() == (False,)
    with psycopg.connect(database.owner) as connection:
        assert (
            connection.execute(
                "SELECT oid,relacl FROM pg_class WHERE "
                "relnamespace IN ('mingjing_core'::regnamespace,'public'::regnamespace) "
                "ORDER BY oid"
            ).fetchall()
            == before
        )


@pytest.mark.parametrize(
    "table", ["core_model_accounts", "core_model_usage", "core_model_batches", "core_model_authorizations"]
)
def test_extra_quota_delete_is_rejected_without_granting_to_match_old_b9_gate(database, table):
    with (
        database.changed(
            f"GRANT DELETE ON mingjing_core.{table} TO {{writer}}",
            f"REVOKE DELETE ON mingjing_core.{table} FROM {{writer}}",
        ),
        pytest.raises(RestoreRejected, match="EXACT_TABLE_ACL"),
    ):
        database.verify()


@pytest.mark.parametrize("table", ["mingjing_core.schema_migrations", "public.checkpoint_migrations"])
def test_migration_ledgers_remain_read_only(database, table):
    with (
        database.changed(f"GRANT INSERT ON {table} TO {{writer}}", f"REVOKE INSERT ON {table} FROM {{writer}}"),
        pytest.raises(RestoreRejected, match="EXACT_TABLE_ACL"),
    ):
        database.verify()


def test_column_only_quota_escalation_is_not_missed(database):
    with (
        database.changed(
            "GRANT UPDATE(account_id) ON mingjing_core.core_model_authorizations TO {writer}",
            "REVOKE UPDATE(account_id) ON mingjing_core.core_model_authorizations FROM {writer}",
        ),
        pytest.raises(RestoreRejected, match="EXACT_COLUMN_ACL"),
    ):
        database.verify()


@pytest.mark.parametrize(
    "grant,revoke,code",
    [
        ("GRANT CREATE ON SCHEMA public TO {writer}", "REVOKE CREATE ON SCHEMA public FROM {writer}", "DDL_TEMP"),
        (
            "GRANT TEMP ON DATABASE {database} TO {writer}",
            "REVOKE TEMP ON DATABASE {database} FROM {writer}",
            "DDL_TEMP",
        ),
        (
            "GRANT DELETE ON mingjing_core.core_model_accounts TO PUBLIC",
            "REVOKE DELETE ON mingjing_core.core_model_accounts FROM PUBLIC",
            "EXACT_TABLE",
        ),
        (
            "REVOKE DELETE ON public.checkpoints FROM {writer}",
            "GRANT DELETE ON public.checkpoints TO {writer}",
            "EXACT_TABLE",
        ),
        (
            "GRANT SELECT ON mingjing_core.core_entities TO {writer} WITH GRANT OPTION",
            "REVOKE GRANT OPTION FOR SELECT ON mingjing_core.core_entities FROM {writer}",
            "EXACT_TABLE",
        ),
        (
            "GRANT UPDATE ON SEQUENCE mingjing_core.core_model_usage_id_seq TO {writer}",
            "REVOKE UPDATE ON SEQUENCE mingjing_core.core_model_usage_id_seq FROM {writer}",
            "EXACT_SEQUENCE",
        ),
    ],
)
def test_privilege_escalations_and_checkpoint_dml_losses_fail_closed(database, grant, revoke, code):
    with database.changed(grant, revoke), pytest.raises(RestoreRejected, match=code):
        database.verify()


def test_writer_role_inheritance_is_rejected_even_without_owner_switch(database):
    with (
        database.changed("GRANT {owner} TO {writer}", "REVOKE {owner} FROM {writer}", admin=True),
        pytest.raises(RestoreRejected, match="ELEVATED_OR_INHERITED_ROLE"),
    ):
        database.verify()


@pytest.mark.parametrize("namespace", ["public", "mingjing_core"])
def test_owner_view_cannot_expose_forbidden_quota_delete_or_update(database, namespace):
    with database.changed(
        f"CREATE VIEW {namespace}.synthetic_quota_bypass AS SELECT * FROM mingjing_core.core_model_authorizations; "
        f"GRANT DELETE,UPDATE ON {namespace}.synthetic_quota_bypass TO {{writer}}",
        f"DROP VIEW {namespace}.synthetic_quota_bypass",
    ):
        with psycopg.connect(database.writer) as connection:
            assert connection.execute(
                "SELECT has_table_privilege(current_user,%s,'DELETE') AND "
                "has_table_privilege(current_user,%s,'UPDATE') AND "
                "NOT has_table_privilege(current_user,'mingjing_core.core_model_authorizations','DELETE') AND "
                "NOT has_table_privilege(current_user,'mingjing_core.core_model_authorizations','UPDATE')",
                (namespace + ".synthetic_quota_bypass", namespace + ".synthetic_quota_bypass"),
            ).fetchone() == (True,)
        with pytest.raises(RestoreRejected, match="UNREVIEWED_RELATION_SURFACE"):
            database.verify()


@pytest.mark.parametrize("kind", ["FUNCTION", "PROCEDURE"])
def test_executable_owner_security_definer_cannot_bypass_quota_acl(database, kind):
    returns = "RETURNS integer" if kind == "FUNCTION" else ""
    body = "BEGIN RETURN 0; END" if kind == "FUNCTION" else "BEGIN NULL; END"
    with database.changed(
        f"CREATE {kind} public.synthetic_quota_bypass() {returns} LANGUAGE plpgsql SECURITY DEFINER "
        f"AS $$ {body} $$; GRANT EXECUTE ON {kind} public.synthetic_quota_bypass() TO {{writer}}",
        f"DROP {kind} public.synthetic_quota_bypass()",
    ):
        with psycopg.connect(database.writer) as connection:
            assert connection.execute(
                "SELECT prosecdef AND has_function_privilege(current_user,oid,'EXECUTE') "
                "FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='synthetic_quota_bypass'"
            ).fetchone() == (True,)
        with pytest.raises(RestoreRejected, match="EXECUTABLE_SECURITY_DEFINER_ROUTINE"):
            database.verify()


def test_default_search_path_catalog_view_cannot_hide_actual_quota_backdoor(database):
    setup = (
        "CREATE VIEW public.quota_bypass AS SELECT * FROM mingjing_core.core_model_authorizations; "
        "GRANT DELETE,UPDATE ON public.quota_bypass TO {writer}; "
        "CREATE SCHEMA acl_spoof AUTHORIZATION {owner}; GRANT USAGE ON SCHEMA acl_spoof TO {writer}; "
        "CREATE VIEW acl_spoof.pg_class AS SELECT * FROM pg_catalog.pg_class "
        "WHERE oid<>'public.quota_bypass'::regclass; GRANT SELECT ON acl_spoof.pg_class TO {writer}"
    )
    cleanup = "DROP VIEW acl_spoof.pg_class; DROP SCHEMA acl_spoof; DROP VIEW public.quota_bypass"
    with database.changed(setup, cleanup), database.default_search_path("writer"):
        with psycopg.connect(database.writer, autocommit=True) as writer:
            assert writer.execute("SHOW search_path").fetchone() == ("acl_spoof, pg_catalog",)
            assert writer.execute("SELECT EXISTS(SELECT 1 FROM pg_class WHERE relname='quota_bypass')").fetchone() == (
                False,
            )
            assert writer.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_class WHERE relname='quota_bypass')"
            ).fetchone() == (True,)
            # Empty predicates prove the effective bypass without changing any business row.
            assert writer.execute("DELETE FROM public.quota_bypass WHERE false").rowcount == 0
            assert (
                writer.execute("UPDATE public.quota_bypass SET authorization_id='synthetic' WHERE false").rowcount == 0
            )
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                writer.execute("DELETE FROM mingjing_core.core_model_authorizations WHERE false")
        with pytest.raises(RestoreRejected, match="UNREVIEWED_RELATION_SURFACE"):
            database.verify()


def test_valid_acl_pins_catalog_despite_both_role_default_search_paths(database):
    with database.default_search_path("owner", "writer"):
        for dsn in (database.owner, database.writer):
            with psycopg.connect(dsn) as connection:
                assert connection.execute("SHOW search_path").fetchone() == ("acl_spoof, pg_catalog",)
        result = database.verify()
        assert result["read_only"] is True and result["quota_tables_checked"] == 4
        assert result["database_connections"] == 2 and result["mutations"] == 0
        assert result["native_restore_completed"] is result["linux_attestation"] is False

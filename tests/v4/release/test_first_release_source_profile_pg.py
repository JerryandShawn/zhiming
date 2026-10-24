"""Actual prefix4/7 source gates and pinned Core SQL; no source adoption or release proof."""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import replace

import psycopg
import pytest
from psycopg import sql
from psycopg.rows import dict_row
from test_first_release_incremental_backup_pg import archive, existing  # noqa: F401

from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental_pg import snapshot
from tools.first_release_migration_steps import forward_core, history, load_bundle
from tools.first_release_source_profile import verify_source_profile


@pytest.fixture
def legal(existing):  # noqa: F811
    """Prepare only this test-owned source, before a capture exists, with legitimate original ACLs."""
    with psycopg.connect(existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        writer = sql.Identifier(existing.inputs.source.database + "_writer")
        owner.execute("DROP SEQUENCE mingjing_core.synthetic_backup_seq")
        owner.execute(sql.SQL("GRANT USAGE ON SCHEMA mingjing_core,public TO {}").format(writer))
        for namespace in ("mingjing_core", "public"):
            owner.execute(
                sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(namespace), writer
                )
            )
        for name in ("mingjing_core.schema_migrations", "public.checkpoint_migrations"):
            owner.execute(
                sql.SQL("REVOKE INSERT,UPDATE,DELETE ON {} FROM {}").format(sql.Identifier(*name.split(".")), writer)
            )
    return existing


@contextmanager
def owner_session(case):
    with psycopg.connect(case.environment["FIRST_INCREMENTAL_OWNER_DSN"], autocommit=True, row_factory=dict_row) as c:
        c.execute("SET search_path=pg_catalog")
        yield c


def profile(case, role="writer"):
    with (
        psycopg.connect(
            case.environment["FIRST_INCREMENTAL_" + role.upper() + "_DSN"], autocommit=True, row_factory=dict_row
        ) as c,
        c.transaction(),
    ):
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        c.execute("SET LOCAL search_path=pg_catalog")
        return verify_source_profile(c, case.inputs, role)


def original_rows(connection, columns, prefix):
    result = {}
    for name, fields in columns.items():
        selection = sql.SQL("SELECT {} FROM {}").format(
            sql.SQL(",").join(sql.Identifier(field["name"]) for field in fields), sql.Identifier(*name.split("."))
        )
        if name == "mingjing_core.schema_migrations":
            selection += sql.SQL(" WHERE version<=%s")
        rows = connection.execute(
            sql.SQL("SELECT to_jsonb(t) AS row FROM ({}) t").format(selection),
            (prefix,) if name == "mingjing_core.schema_migrations" else (),
        )
        result[name] = sorted(json.dumps(row["row"], sort_keys=True) for row in rows)
    return result


def forward_preserving(case):
    expected_prefix = len(case.inputs.source.migrations)
    assert profile(case, "owner")["prefix"] == profile(case)["prefix"] == expected_prefix
    bundle = load_bundle(case.inputs.release, case.inputs.candidate_source)
    with owner_session(case) as owner:
        with owner.transaction():
            before = snapshot(owner)
            rows = original_rows(owner, before["columns"], expected_prefix)

        def locked(c):
            assert c.execute("SHOW transaction_isolation").fetchone() == {"transaction_isolation": "read committed"}
            for name in sorted(before["tables"]):
                c.execute(
                    sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(sql.Identifier(*name.split(".")))
                )
            verify_source_profile(c, case.inputs, "owner")
            assert snapshot(c) == before, "SOURCE_CHANGED_BEFORE_FORWARD"

        assert forward_core(owner, bundle, case.inputs.source.migrations, prepare_locked_source=locked) == list(
            range(expected_prefix + 1, 9)
        )
        with owner.transaction():
            after = snapshot(owner)
            assert history(owner) == {int(v): checksum for v, checksum in case.inputs.release.migrations}
            assert original_rows(owner, before["columns"], expected_prefix) == rows, "FORWARD_CHANGED_ORIGINAL_FIELDS"
            assert set(after["sequences"]) == {"mingjing_core.core_model_usage_id_seq"}
            quota = after["sequences"]["mingjing_core.core_model_usage_id_seq"]
            assert quota["last_value"] == 1 and quota["is_called"] is False
            for table in ("accounts", "usage", "batches", "authorizations"):
                assert owner.execute("SELECT count(*) AS count FROM mingjing_core.core_model_" + table).fetchone() == {
                    "count": 0
                }


class ObservedSQL:
    """Observe actual PG outcomes without substituting a database or changing the reviewed SQL."""

    def __init__(self, connection):
        self.connection, self.runtime_created, self.failure_code = connection, False, None

    def transaction(self):
        return self.connection.transaction()

    def execute(self, statement, *arguments):
        try:
            result = self.connection.execute(statement, *arguments)
        except psycopg.Error as error:
            self.failure_code = error.sqlstate
            raise
        if isinstance(statement, str) and "CREATE TABLE core_run_events(" in statement:
            self.runtime_created = True
        return result


@pytest.mark.parametrize("existing", [4], indirect=True)
def test_prefix4_profile_and_forward_preserve_all_original_fields(legal):
    forward_preserving(legal)


@pytest.mark.parametrize("existing", [7], indirect=True)
def test_prefix7_profile_and_forward_preserve_all_original_fields(legal):
    forward_preserving(legal)


def test_wrong_or_disabled_actual_retirement_trigger_is_rejected(legal):
    assert profile(legal)["retirement_trigger_checked"] is True
    with owner_session(legal) as owner:
        for mutation in (
            "ALTER TABLE mingjing_core.core_entities DISABLE TRIGGER core_embedding_retirement",
            "DROP TRIGGER core_embedding_retirement ON mingjing_core.core_entities; "
            "CREATE TRIGGER core_embedding_retirement AFTER UPDATE OF status ON mingjing_core.core_entities "
            "FOR EACH ROW EXECUTE FUNCTION mingjing_core.clear_retired_embeddings()",
        ):
            with pytest.raises(RestoreRejected, match="SOURCE_PROFILE7_TRIGGER"), owner.transaction():
                owner.execute(mutation)
                verify_source_profile(owner, legal.inputs, "owner")
    assert profile(legal)["retirement_trigger_checked"] is True


def test_public_database_or_schema_grants_are_rejected(legal):
    with owner_session(legal) as owner:
        database = sql.Identifier(legal.inputs.source.database)
        for grant, revoke in (
            (
                sql.SQL("GRANT CONNECT ON DATABASE {} TO PUBLIC").format(database),
                sql.SQL("REVOKE CONNECT ON DATABASE {} FROM PUBLIC").format(database),
            ),
            (sql.SQL("GRANT CREATE ON SCHEMA public TO PUBLIC"), sql.SQL("REVOKE CREATE ON SCHEMA public FROM PUBLIC")),
        ):
            owner.execute(grant)
            try:
                with pytest.raises(RestoreRejected, match="SOURCE_PROFILE_(PUBLIC_DATABASE|WRITER_DDL)"):
                    profile(legal)
            finally:
                owner.execute(revoke)
    assert profile(legal)["prefix"] == 7


def test_writer_missing_dml_or_mutable_migration_ledger_is_rejected(legal):
    with owner_session(legal) as owner:
        writer = sql.Identifier(legal.inputs.source.database + "_writer")
        for mutate, restore in (
            (
                "REVOKE DELETE ON mingjing_core.core_entities FROM {}",
                "GRANT DELETE ON mingjing_core.core_entities TO {}",
            ),
            (
                "GRANT INSERT ON mingjing_core.schema_migrations TO {}",
                "REVOKE INSERT ON mingjing_core.schema_migrations FROM {}",
            ),
        ):
            owner.execute(sql.SQL(mutate).format(writer))
            try:
                with pytest.raises(RestoreRejected, match="EXACT_TABLE_ACL_MISMATCH"):
                    profile(legal)
            finally:
                owner.execute(sql.SQL(restore).format(writer))
    assert profile(legal)["prefix"] == 7


def test_unreviewed_relation_or_executable_security_definer_is_rejected(legal):
    with owner_session(legal) as owner:
        for mutation, error in (
            (
                "CREATE VIEW public.unreviewed_source AS SELECT * FROM mingjing_core.core_entities",
                "SOURCE_PROFILE_RELATIONS_OR_SEQUENCE",
            ),
            (
                "CREATE FUNCTION public.unreviewed_source() RETURNS integer LANGUAGE sql SECURITY DEFINER "
                "AS 'SELECT 1'",
                "SOURCE_PROFILE_EXECUTABLE_DEFINER",
            ),
        ):
            with pytest.raises(RestoreRejected, match=error), owner.transaction():
                owner.execute(mutation)
                verify_source_profile(owner, legal.inputs, "owner")
    assert profile(legal)["prefix"] == 7


@pytest.mark.parametrize("existing", [4], indirect=True)
def test_actual_0006_index_cast_failure_rolls_back_complete_core_transaction(legal):
    with owner_session(legal) as owner:
        owner.execute(
            "UPDATE mingjing_core.core_entities SET data=jsonb_set(data,'{at_ms}','\"not-an-integer\"') "
            "WHERE kind='message'"
        )
        assert profile(legal)["prefix"] == 4
        with owner.transaction():
            before = snapshot(owner)
        bundle = load_bundle(legal.inputs.release, legal.inputs.candidate_source)
        observed = ObservedSQL(owner)
        with pytest.raises(RestoreRejected, match="FORWARD_CORE_TRANSACTION_FAILED"):
            forward_core(observed, bundle, legal.inputs.source.migrations)
        assert observed.runtime_created is True and observed.failure_code == "22P02"
        with owner.transaction():
            assert snapshot(owner) == before, "FAILED_CORE_TX_CHANGED_FULL_SOURCE_STATE"
            assert max(history(owner)) == 4
            assert owner.execute("SELECT to_regclass('mingjing_core.core_run_steps') AS relation").fetchone() == {
                "relation": None
            }
            assert owner.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='mingjing_core.core_runs'::regclass "
                "AND attname='runtime' AND NOT attisdropped) AS found"
            ).fetchone() == {"found": False}


def test_actual_database_oid_mismatch_is_rejected_without_writes(legal):
    wrong = replace(
        legal.inputs, source=replace(legal.inputs.source, database_oid=legal.inputs.source.database_oid + 1)
    )
    with owner_session(legal) as owner, owner.transaction():
        before = snapshot(owner)
        with pytest.raises(RestoreRejected, match="SOURCE_PROFILE_ACTUAL_IDENTITY"):
            verify_source_profile(owner, wrong, "owner")
        assert snapshot(owner) == before, "IDENTITY_REJECTION_CHANGED_FULL_SOURCE_STATE"

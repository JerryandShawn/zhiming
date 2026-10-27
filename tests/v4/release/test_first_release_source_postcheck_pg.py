"""Real synthetic-source forward fixtures and read-only postchecks; no source upgrade authority."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.rows import dict_row
from test_first_release_capture_binding_pg import source_document
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_source_profile_pg import legal as shared_legal

from tools.first_release_contracts import RestoreRejected
from tools.first_release_incremental import BackupInputs
from tools.first_release_incremental_pg import snapshot
from tools.first_release_migration_steps import forward_core, grant_new_runtime, history, load_bundle
from tools.first_release_source_postcheck import original_fields, owner_state, writer_state
from tools.first_release_source_profile import verify_source_profile


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


@dataclass
class Prepared:
    source: Any
    baseline: dict[str, Any]
    checkpoint_versions: tuple[int, ...]
    saver_count: int


@contextmanager
def session(case, role="owner", *, readonly=True, isolation="REPEATABLE READ"):
    variable = "FIRST_INCREMENTAL_" + role.upper() + "_DSN"
    with psycopg.connect(case.source.environment[variable], autocommit=True, row_factory=dict_row) as connection:
        connection.execute("SET search_path=pg_catalog")
        with connection.transaction():
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL " + isolation + (", READ ONLY" if readonly else ", READ WRITE")
            )
            yield connection


def final_snapshot(case):
    with session(case) as owner:
        return snapshot(owner)


def inspect_owner(case):
    with session(case) as owner:
        return owner_state(
            owner,
            case.source.inputs,
            case.baseline,
            case.checkpoint_versions,
            saver_count=case.saver_count,
            allowed_pids={owner.info.backend_pid},
        )


def inspect_writer(case):
    with session(case, "writer") as writer:
        return writer_state(writer, case.source.inputs, allowed_pids={writer.info.backend_pid})


@pytest.fixture
def prepared(existing):
    source = shared_legal.__wrapped__(existing)
    source.inputs = BackupInputs.parse(source_document(source.inputs), source.inputs.workspace)
    with psycopg.connect(
        source.environment["FIRST_INCREMENTAL_OWNER_DSN"], autocommit=True, row_factory=dict_row
    ) as owner:
        owner.execute("SET search_path=pg_catalog")
        owner.execute("SET TimeZone='Asia/Tokyo'")
        with owner.transaction():
            owner.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            verify_source_profile(owner, source.inputs, "owner")
            baseline = snapshot(owner)
            versions = tuple(row["v"] for row in owner.execute("SELECT v FROM public.checkpoint_migrations ORDER BY v"))
            assert history(owner) == {int(v): checksum for v, checksum in source.inputs.source.migrations}
        bundle = load_bundle(source.inputs.release, source.inputs.candidate_source)

        def locked(connection):
            for name in sorted(baseline["tables"]):
                connection.execute(
                    sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE NOWAIT").format(sql.Identifier(*name.split(".")))
                )
            verify_source_profile(connection, source.inputs, "owner")
            assert snapshot(connection) == baseline

        assert forward_core(owner, bundle, source.inputs.source.migrations, prepare_locked_source=locked) == list(
            range(len(source.inputs.source.migrations) + 1, 9)
        )
        with owner.transaction():
            owner.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            original_fields(owner, source.inputs, baseline, versions)
        owner.execute("SET search_path=public")
        PostgresSaver(owner).setup()
        owner.execute("SET search_path=pg_catalog")
        grant_new_runtime(owner, source.inputs.source.database + "_writer")
        assert history(owner) == {int(v): checksum for v, checksum in source.inputs.release.migrations}
        actual = tuple(row["v"] for row in owner.execute("SELECT v FROM public.checkpoint_migrations ORDER BY v"))
        assert actual == tuple(range(len(PostgresSaver.MIGRATIONS)))
    return Prepared(source, baseline, versions, len(PostgresSaver.MIGRATIONS))


@pytest.mark.parametrize("existing", [4, 7], indirect=True)
def test_actual_forward_sdk_grants_and_owner_writer_postchecks_preserve_old_fields(prepared, record_property):
    record_property("sdk_checkpoint_versions_before", len(prepared.checkpoint_versions))
    record_property("sdk_checkpoint_versions_after", prepared.saver_count)
    record_property("sdk_new_migration_versions", prepared.saver_count - len(prepared.checkpoint_versions))
    before = final_snapshot(prepared)
    observed_owner, observed_writer = inspect_owner(prepared), inspect_writer(prepared)
    assert (
        observed_owner["database_oid"] == observed_writer["database_oid"] == prepared.source.inputs.source.database_oid
    )
    assert observed_owner["owner_role_oid"] == prepared.source.inputs.source.owner_oid
    assert observed_writer["writer_role_oid"] == prepared.source.inputs.source.writer_oid
    assert observed_owner["original_fields_verified"] is True
    assert observed_owner["checkpoint_migrations_checked"] == prepared.saver_count
    assert observed_owner["central_ledger_empty"] is observed_owner["central_sequence_unused"] is True
    assert observed_writer["quota_tables_checked"] == 4 and observed_writer["sequences_checked"] == 1
    for result in (observed_owner, observed_writer):
        for name in (
            "source_write_authorized",
            "global_quiescence_verified",
            "runtime_verified",
            "linux_attestation",
            "publication",
        ):
            assert result[name] is False
    assert final_snapshot(prepared) == before, "READONLY_POSTCHECK_CHANGED_REAL_SOURCE"


def test_original_timestamp_drift_is_rejected_and_never_repaired(prepared):
    with session(prepared, readonly=False) as owner:
        assert (
            owner.execute(
                "UPDATE mingjing_core.core_entities SET updated_at=updated_at+interval '1 second' "
                "WHERE owner='synthetic' AND kind='message' AND id='synthetic-message'"
            ).rowcount
            == 1
        )
    faulty = final_snapshot(prepared)
    with pytest.raises(RestoreRejected, match="^SOURCE_POSTCHECK_ORIGINAL_FIELDS_CHANGED$"):
        inspect_owner(prepared)
    assert final_snapshot(prepared) == faulty, "POSTCHECK_REPAIRED_CHANGED_ORIGINAL_TIMESTAMP"


def test_original_column_type_and_nullability_drift_are_rejected_without_repairs(prepared):
    with session(prepared) as owner:
        subjects = owner.execute(
            "SELECT count(*) AS count,max(length(label)) AS longest FROM mingjing_core.core_subjects"
        ).fetchone()
        assert subjects["count"] > 0 and 0 < subjects["longest"] <= 64
    for table, mutate, restore in (
        (
            "core_subjects",
            "ALTER COLUMN label TYPE varchar(64) USING label::varchar(64)",
            "ALTER COLUMN label TYPE text USING label::text",
        ),
        ("core_entities", "ALTER COLUMN updated_at DROP NOT NULL", "ALTER COLUMN updated_at SET NOT NULL"),
    ):
        with session(prepared, readonly=False) as owner:
            owner.execute(sql.SQL("ALTER TABLE {} {}").format(sql.Identifier("mingjing_core", table), sql.SQL(mutate)))
        try:
            faulty = final_snapshot(prepared)
            with pytest.raises(RestoreRejected, match="^SOURCE_POSTCHECK_ORIGINAL_COLUMN_CHANGED$"):
                inspect_owner(prepared)
            assert final_snapshot(prepared) == faulty, "POSTCHECK_REPAIRED_REAL_COLUMN_FAULT"
        finally:
            # Cleanup only this fixture's deliberate fault after checking the helper did not repair it.
            with session(prepared, readonly=False) as owner:
                owner.execute(
                    sql.SQL("ALTER TABLE {} {}").format(sql.Identifier("mingjing_core", table), sql.SQL(restore))
                )


def quota_right(case, privilege):
    with session(case) as owner:
        return owner.execute(
            "SELECT has_table_privilege(%s,'mingjing_core.core_model_accounts',%s) AS allowed",
            (case.source.inputs.source.database + "_writer", privilege),
        ).fetchone()["allowed"]


def test_quota_delete_and_grant_option_are_rejected_and_never_repaired(prepared):
    role = sql.Identifier(prepared.source.inputs.source.database + "_writer")
    for mutate, restore, privilege in (
        (
            "GRANT DELETE ON mingjing_core.core_model_accounts TO {}",
            "REVOKE DELETE ON mingjing_core.core_model_accounts FROM {}",
            "DELETE",
        ),
        (
            "GRANT SELECT ON mingjing_core.core_model_accounts TO {} WITH GRANT OPTION",
            "REVOKE GRANT OPTION FOR SELECT ON mingjing_core.core_model_accounts FROM {}",
            "SELECT WITH GRANT OPTION",
        ),
    ):
        with session(prepared, readonly=False) as owner:
            owner.execute(sql.SQL(mutate).format(role))
        try:
            assert quota_right(prepared, privilege) is True
            with pytest.raises(RestoreRejected, match="^EXACT_TABLE_ACL_MISMATCH$"):
                inspect_writer(prepared)
            assert quota_right(prepared, privilege) is True, "POSTCHECK_REPAIRED_REAL_QUOTA_ACL_FAULT"
        finally:
            with session(prepared, readonly=False) as owner:
                owner.execute(sql.SQL(restore).format(role))


def test_actual_usage_sequence_nextval_is_rejected_and_never_reset(prepared):
    with session(prepared, readonly=False) as owner:
        owner.execute("SELECT nextval('mingjing_core.core_model_usage_id_seq')")
    faulty = final_snapshot(prepared)
    assert faulty["sequences"]["mingjing_core.core_model_usage_id_seq"]["is_called"] is True
    with pytest.raises(RestoreRejected, match="^SOURCE_POSTCHECK_CENTRAL_SEQUENCE_USED$"):
        inspect_owner(prepared)
    assert final_snapshot(prepared) == faulty, "POSTCHECK_RESET_REAL_USAGE_SEQUENCE"


def test_nonreadonly_nonrepeatable_or_wrong_pid_scope_is_rejected_without_writes(prepared):
    before = final_snapshot(prepared)
    for readonly, isolation in ((False, "REPEATABLE READ"), (True, "READ COMMITTED")):
        with (
            session(prepared, readonly=readonly, isolation=isolation) as owner,
            pytest.raises(RestoreRejected, match="^SOURCE_POSTCHECK_READONLY_CATALOG_REQUIRED$"),
        ):
            original_fields(owner, prepared.source.inputs, prepared.baseline, prepared.checkpoint_versions)
    with (
        session(prepared) as owner,
        pytest.raises(RestoreRejected, match="^SOURCE_POSTCHECK_EXPLICIT_PIDS_REQUIRED$"),
    ):
        owner_state(
            owner,
            prepared.source.inputs,
            prepared.baseline,
            prepared.checkpoint_versions,
            saver_count=prepared.saver_count,
            allowed_pids=set(),
        )
    assert final_snapshot(prepared) == before, "REJECTED_READ_SCOPE_CHANGED_REAL_SOURCE"

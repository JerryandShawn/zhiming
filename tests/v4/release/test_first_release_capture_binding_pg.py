"""New UTC captures compared with actual original restores before any forward migration."""

from __future__ import annotations

import json
import secrets
import shutil
import uuid
from dataclasses import dataclass, field, replace

import psycopg
import pytest
from first_release_support import pin_document, write_json
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from test_first_release_incremental_backup_pg import archive as archive
from test_first_release_incremental_backup_pg import existing as existing
from test_first_release_local_restore_pg import pg_program

from tools import first_release_incremental_pg as incremental_pg
from tools import first_release_local_restore as restore
from tools.first_release_capture_binding import CONTROLS, CaptureBinding, CaptureBindingPin
from tools.first_release_contracts import RestoreContract, RestoreRejected
from tools.first_release_incremental import HERE, file_hash
from tools.first_release_incremental import execute as capture
from tools.first_release_local_inputs import DumpPin, LocalInputs


@dataclass
class CaptureCase:
    source: object
    inputs: LocalInputs
    binding: CaptureBinding
    environment: dict = field(repr=False)


def source_document(inputs):
    source = inputs.source
    return {
        "schema": "first-release-local-incremental-backup-pin-v1",
        "operation_id": inputs.operation_id,
        "local_drill": True,
        "release": pin_document(inputs.release),
        "source": {
            "database": source.database,
            "system_identifier": source.system_identifier,
            "database_oid": source.database_oid,
            "owner_oid": source.owner_oid,
            "writer_oid": source.writer_oid,
            "owners": list(source.owners),
            "migrations": dict(source.migrations),
        },
        "runtime": {
            "python": str(inputs.python),
            "pg_dump": str(inputs.pg_dump),
            "python_sha256": inputs.python_sha256,
            "pg_dump_sha256": inputs.pg_dump_sha256,
        },
        "controls": dict(inputs.controls),
    }


def binding_pin(source, inputs):
    path = source.inputs.operation_dir
    receipt = json.loads((path / "backup-receipt.json").read_text())
    return CaptureBindingPin(
        inputs.release.candidate,
        inputs.release.manifest_sha256,
        file_hash(path / "capture-inputs.json"),
        file_hash(path / "backup-receipt.json"),
        receipt["source_state_sha256"],
        receipt["dump_sha256"],
        receipt["ledger_sha256"],
        inputs.contract.operation_id,
        tuple(sorted((name, file_hash(HERE / name)) for name in CONTROLS)),
    )


def capture_with_session_diagnostic(source):
    original = incremental_pg.sessions

    def checked(connection, allowed):
        try:
            return original(connection, allowed)
        except RestoreRejected as error:
            if str(error) == "INCREMENTAL_OTHER_SOURCE_SESSION":
                try:
                    connection.execute("SELECT pg_stat_clear_snapshot()")
                    rows = connection.execute(
                        "SELECT pid,backend_type FROM pg_stat_activity WHERE datname=current_database() ORDER BY pid"
                    ).fetchall()
                    # This fresh observation is later than the failed gate, not its original PID set.
                    print(
                        json.dumps(
                            {
                                "schema": "capture-session-diagnostic-v1",
                                "observation": "after_rejection_current",
                                "allowed_pids": sorted(allowed),
                                "current_backends": rows,
                            },
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                except Exception:
                    raise error from None
            raise

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(incremental_pg, "sessions", checked)
        return capture(source.inputs, backup_local=True, environment=source.environment)


@pytest.fixture
def captured(existing, request):  # noqa: F811 - pytest resolves the imported fixture by this parameter name.
    source = existing
    if getattr(request, "param", None) == "core-only":
        # The migration ACL deliberately excludes M1's extra sequence fixture; change the source before capture.
        with psycopg.connect(source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
            owner.execute("DROP SEQUENCE mingjing_core.synthetic_backup_seq")
    source_pin = source.inputs.operation_dir / "capture-inputs.json"
    write_json(source_pin, source_document(source.inputs))
    with psycopg.connect(source.admin, autocommit=True) as admin:
        admin.execute(
            sql.SQL("ALTER ROLE {} SET TimeZone='Asia/Tokyo'").format(
                sql.Identifier(source.inputs.source.database + "_owner")
            )
        )
    with psycopg.connect(source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        assert owner.execute("SHOW TimeZone").fetchone() == ("Asia/Tokyo",)
    receipt = capture_with_session_diagnostic(source)
    assert receipt["source_projection"] == "postgres-jsonb-utc-v1"
    ident = uuid.uuid4().hex
    release = source.inputs.release
    root = source.inputs.workspace / "private" / ("first-release-" + ident) / release.candidate
    shutil.copytree(source.inputs.candidate_source, root)
    dump = root.parent / "backup.dump"
    shutil.copyfile(source.inputs.operation_dir / "backup.dump", dump)
    contract = RestoreContract("fr-" + ident, "fr_restore_" + ident, root, local_drill=True)
    program = pg_program("pg_restore")
    inputs = LocalInputs(
        release,
        contract,
        DumpPin(
            release.candidate,
            release.manifest_sha256,
            receipt["dump_sha256"],
            file_hash(program),
            source.inputs.source.migrations,
        ),
        dump,
        program,
        source.inputs.workspace,
    )
    location = conninfo_to_dict(source.admin)
    env = {"FIRST_RELEASE_ADMIN_DSN": source.admin}
    for role in ("owner", "writer"):
        env["FIRST_RELEASE_" + role.upper() + "_DSN"] = make_conninfo(
            host=location["host"],
            port=location["port"],
            dbname=contract.database,
            user=contract.database + "_" + role,
            password=secrets.token_urlsafe(24),
        )
    try:
        yield CaptureCase(source, inputs, CaptureBinding(source_pin, binding_pin(source, inputs)), env)
    finally:
        with psycopg.connect(source.admin, autocommit=True) as admin:
            if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (contract.database,)).fetchone():
                admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(contract.database)))
            for role in ("owner", "writer"):
                name = contract.database + "_" + role
                if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone():
                    admin.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(name)))


def apply(case):
    return restore.execute(
        case.inputs, apply_local=True, upgrade_local=True, capture_binding=case.binding, environment=case.environment
    )


def customize_actual_restore(case, monkeypatch, mutate=None):
    original = restore.run_program

    def observed(inputs, arguments, environment):
        result = original(inputs, arguments, environment)
        if arguments[0].startswith("--host="):
            with psycopg.connect(case.source.admin, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("ALTER ROLE {} SET TimeZone='America/New_York'").format(
                        sql.Identifier(inputs.contract.database + "_owner")
                    )
                )
            with psycopg.connect(case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
                assert owner.execute("SHOW TimeZone").fetchone() == ("America/New_York",)
                if mutate is not None:
                    mutate(owner)
        return result

    monkeypatch.setattr(restore, "run_program", observed)


def assert_original_retained(case):
    with psycopg.connect(case.environment["FIRST_RELEASE_OWNER_DSN"]) as owner:
        assert owner.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone() == (
            len(case.inputs.dump_pin.source_migrations),
        )
        assert owner.execute("SELECT to_regclass('mingjing_core.core_model_accounts')").fetchone() == (None,)


@pytest.mark.parametrize("existing", [4, 7], indirect=True)
@pytest.mark.parametrize("captured", ["core-only"], indirect=True)
def test_true_capture_to_fresh_original_restore_then_upgrade_has_utc_and_complete_column_binding(captured, monkeypatch):
    customize_actual_restore(captured, monkeypatch)
    result = apply(captured)
    proof = result["capture_binding"]
    assert proof["local_original_content_verified"] is proof["local_capture_binding_verified"] is True
    assert proof["source_projection"] == "postgres-jsonb-utc-v1" and proof["tables_checked"] > 10
    assert proof["sequences_checked"] == 0 and proof["sequence_log_cnt_cross_restore_equality_required"] is False
    assert result["database_connections"] == 8 and result["local_upgrade_completed"] is True
    assert result["upgraded_migrations"] == dict(captured.inputs.release.migrations)
    assert captured.inputs.contract.database != captured.source.inputs.source.database
    for key in (
        "source_restore_content_verified",
        "native_restore_completed",
        "runtime_verified",
        "central_binding_verified",
        "linux_attestation",
        "publication",
    ):
        assert proof[key] is False
    assert result["source_restore_content_verified"] is result["native_restore_completed"] is False
    path = captured.source.inputs.operation_dir / "backup-receipt.json"
    saved = json.loads(path.read_text())
    assert saved["source_snapshots"]["before"]["sequences"] == {}
    assert file_hash(path) == captured.binding.pin.capture_receipt_sha256


def test_old_capture_without_explicit_utc_cannot_be_relabelled_by_new_review_hash(captured):
    path = captured.source.inputs.operation_dir / "backup-receipt.json"
    value = json.loads(path.read_text())
    value.pop("source_projection")
    write_json(path, value)
    captured.binding = replace(
        captured.binding, pin=replace(captured.binding.pin, capture_receipt_sha256=file_hash(path))
    )
    with pytest.raises(RestoreRejected, match="CAPTURE_EXPLICIT_UTC_PROJECTION_REQUIRED"):
        apply(captured)


def test_actual_capture_ledger_bytes_must_still_match_reviewed_capture(captured):
    path = captured.source.inputs.operation_dir / "latest-withdrawals.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(RestoreRejected, match="CAPTURE_ARTIFACT_CHANGED"):
        apply(captured)


def test_timestamp_field_drift_is_detected_before_forward_upgrade_and_retains_original(captured, monkeypatch):
    def change(owner):
        owner.execute("UPDATE mingjing_core.core_entities SET updated_at=updated_at+interval '1 second'")

    customize_actual_restore(captured, monkeypatch, change)
    with pytest.raises(RestoreRejected, match="CAPTURE_RESTORED_TABLE_FIELDS_DIFFER"):
        apply(captured)
    assert_original_retained(captured)


def test_empty_table_column_drift_is_detected_even_when_row_hash_is_still_empty(captured, monkeypatch):
    def change(owner):
        assert owner.execute("SELECT count(*) FROM mingjing_core.core_versions").fetchone() == (0,)
        owner.execute("ALTER TABLE mingjing_core.core_versions ADD COLUMN synthetic_extra text")

    customize_actual_restore(captured, monkeypatch, change)
    with pytest.raises(RestoreRejected, match="CAPTURE_RESTORED_COLUMNS_DIFFER"):
        apply(captured)
    assert_original_retained(captured)


def test_sequence_semantic_drift_cannot_be_hidden_by_valid_table_rows(captured, monkeypatch):
    customize_actual_restore(
        captured,
        monkeypatch,
        lambda owner: owner.execute("SELECT setval('mingjing_core.synthetic_backup_seq',99,true)"),
    )
    with pytest.raises(RestoreRejected, match="CAPTURE_RESTORED_SEQUENCE_SEMANTICS_DIFFER"):
        apply(captured)
    assert_original_retained(captured)


def test_binding_requires_same_call_and_exact_original_source_lineage_without_connections(captured, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("CAPTURE_VALIDATION_MUST_NOT_CONNECT_OR_SPAWN")

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(restore.subprocess, "run", forbidden)
        result = restore.execute(captured.inputs)
        assert result["database_connections"] == result["mutations"] == 0
        with pytest.raises(RestoreRejected, match="CAPTURE_BINDING_REQUIRES_SAME_CALL_APPLY"):
            restore.execute(captured.inputs, capture_binding=captured.binding)
        wrong_target = replace(
            captured.binding, pin=replace(captured.binding.pin, target_operation_id="fr-" + "a" * 32)
        )
        with pytest.raises(RestoreRejected, match="CAPTURE_TARGET_OPERATION_BINDING"):
            wrong_target.validate(captured.inputs)
        path = captured.binding.capture_inputs
        value = json.loads(path.read_text())
        value["source"]["database_oid"] += 10000
        write_json(path, value)
        wrong_source = replace(
            captured.binding, pin=replace(captured.binding.pin, capture_inputs_sha256=file_hash(path))
        )
        with pytest.raises(RestoreRejected, match="CAPTURE_ACTUAL_LINEAGE_BINDING"):
            wrong_source.validate(captured.inputs)

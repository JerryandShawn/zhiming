"""Synthetic same-call source-forward scenarios; native PG and SDK, no release authority."""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
import subprocess
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest
from langgraph.checkpoint import postgres
from langgraph.checkpoint.postgres import base
from psycopg import sql
from psycopg.rows import dict_row
from test_first_release_capture_binding_pg import captured as shared_captured
from test_first_release_capture_binding_pg import source_document
from test_first_release_incremental_backup_pg import archive as shared_archive
from test_first_release_incremental_backup_pg import existing as shared_existing
from test_first_release_incremental_backup_pg import state
from test_first_release_source_profile_pg import legal as shared_legal

from tools import first_release_candidate_process as candidate
from tools import first_release_incremental_forward as forward
from tools import first_release_incremental_scope as scopes
from tools import first_release_target_proof as target_proofs
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_contracts import RestoreRejected
from tools.first_release_controller_runtime import ControllerRuntimePin
from tools.first_release_incremental import BackupInputs, file_hash
from tools.first_release_target_proof import TargetProofPin, target_binding


@pytest.fixture(scope="module", name="archive")
def archive_fixture():
    return shared_archive.__wrapped__()


@pytest.fixture(name="existing")
def source_fixture(request, archive):
    yield from shared_existing.__wrapped__(request, archive)


def runtime_pin(source):
    migrations = postgres.PostgresSaver.MIGRATIONS
    return ControllerRuntimePin(
        source.release.candidate,
        source.release.manifest_sha256,
        dict(source.release.locks)["requirements-core.lock"],
        file_hash(forward.ROOT / "tools/first_release_controller_runtime.py"),
        source.python_sha256,
        metadata.version("langgraph-checkpoint-postgres"),
        file_hash(Path(postgres.__file__)),
        file_hash(Path(base.__file__)),
        hashlib.sha256(json.dumps(migrations, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest(),
        len(migrations),
    )


def request_pin(request):
    binding = forward.forward_binding(
        request.source, request.target, request.capture, request.replay, request.target_pin, request.runtime_pin
    )
    return forward.SourceForwardPin(
        binding, tuple(sorted((name, file_hash(forward.ROOT / name)) for name in forward.CONTROLS))
    )


@pytest.fixture
def proposal(existing):
    source = shared_legal.__wrapped__(existing)
    source.inputs = BackupInputs.parse(source_document(source.inputs), source.inputs.workspace)
    # shared_legal already removed the extra sequence, so never request a second core-only DROP.
    with contextmanager(shared_captured.__wrapped__)(source, SimpleNamespace()) as case:
        ledger = case.inputs.contract.candidate_source.parent / "latest-withdrawals.json"
        ledger.write_bytes((source.inputs.operation_dir / "latest-withdrawals.json").read_bytes())
        replay = CandidateReplay.parse(
            source.inputs.python,
            ledger,
            dict(
                schema="first-release-local-replay-pin-v1",
                candidate=case.inputs.release.candidate,
                manifest_sha256=case.inputs.release.manifest_sha256,
                dump_sha256=case.inputs.dump_pin.dump_sha256,
                ledger_sha256=file_hash(ledger),
                python_sha256=source.inputs.python_sha256,
                worker_sha256=file_hash(candidate.WORKER),
                effects_sha256=file_hash(candidate.EFFECTS),
            ),
        )
        target = TargetProofPin(
            target_binding(case.inputs, case.binding, replay),
            tuple(sorted((name, file_hash(target_proofs.ROOT / name)) for name in target_proofs.CONTROLS)),
        )
        values = dict(
            source=source.inputs,
            target=case.inputs,
            capture=case.binding,
            replay=replay,
            target_pin=target,
            runtime_pin=runtime_pin(source.inputs),
            environment=dict(source.environment, **case.environment),
        )
        pin = request_pin(SimpleNamespace(**values))
        request = forward.ForwardInputs(**values, pin=pin)
        yield SimpleNamespace(case=case, request=request, before=state(source), material=materials(case))


def materials(case):
    source = case.source.inputs
    return {
        str(path): (path.stat().st_ino, path.read_bytes())
        for path in (source.fence_path, source.maintenance, source.operation_dir / "backup-started.json")
    }


def source_rows(value, checkpoint_count=None):
    result = {}
    with psycopg.connect(value.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"], row_factory=dict_row) as owner:
        owner.execute("SET LOCAL TimeZone='UTC'")
        for name, columns in value.before["columns"].items():
            selection = sql.SQL("SELECT {} FROM {}").format(
                sql.SQL(",").join(sql.Identifier(row["name"]) for row in columns), sql.Identifier(*name.split("."))
            )
            args = ()
            if name == "mingjing_core.schema_migrations":
                selection += sql.SQL(" WHERE version<=%s")
                args = (len(value.request.source.source.migrations),)
            elif name == "public.checkpoint_migrations" and checkpoint_count is not None:
                selection += sql.SQL(" WHERE v<%s")
                args = (checkpoint_count,)
            query = sql.SQL("SELECT to_jsonb(t) AS row FROM ({}) t").format(selection)
            result[name] = sorted(json.dumps(row["row"], sort_keys=True) for row in owner.execute(query, args))
    return result


def prefix(value):
    with psycopg.connect(value.case.source.environment["FIRST_INCREMENTAL_OWNER_DSN"]) as owner:
        return owner.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone()[0]


def test_default_has_no_connections_processes_or_writes(proposal, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("DEFAULT_SOURCE_FORWARD_MUST_ONLY_READ_REVIEWED_FILES")

    with monkeypatch.context() as patch:
        patch.setattr(psycopg, "connect", forbidden)
        patch.setattr(subprocess, "run", forbidden)
        result = forward.execute(proposal.request)
    assert result["database_connections"] == result["processes"] == result["file_writes"] == 0
    assert result["source_forward_completed"] is result["source_upgraded"] is False
    assert state(proposal.case.source) == proposal.before and materials(proposal.case) == proposal.material


@pytest.mark.parametrize("existing", [4, 7], indirect=True)
def test_real_same_call_target_runtime_and_source_forward_preserve_original_fields(proposal, record_property):
    before_rows = source_rows(proposal)
    old_versions = len(before_rows["public.checkpoint_migrations"])
    result = forward.execute(proposal.request, apply_source=True)
    assert result["phase"] == "source_forward_completed" and result["source_forward_completed"] is True
    assert result["source_upgraded"] is False and result["privacy_replay_pending"] is result["backfill_pending"] is True
    assert result["controller_runtime"]["controller_runtime_verified"] is True
    assert result["target_proof"]["target_proof_consumed"] is True
    assert result["owner_postcheck"]["original_fields_verified"] is True
    assert result["writer_postcheck"]["quota_tables_checked"] == 4
    assert prefix(proposal) == 8 and source_rows(proposal, old_versions) == before_rows
    assert materials(proposal.case) == proposal.material
    final = state(proposal.case.source)
    for name in ("accounts", "usage", "authorizations", "batches"):
        assert final["tables"]["mingjing_core.core_model_" + name] == hashlib.sha256(b"[]").hexdigest()
    assert final["sequences"]["mingjing_core.core_model_usage_id_seq"] == dict(last_value=1, log_cnt=0, is_called=False)
    for name in (
        "source_write_authorized",
        "native_restore_completed",
        "runtime_verified",
        "central_binding_verified",
        "publication",
        "linux_attestation",
        "global_quiescence_verified",
    ):
        assert result[name] is False
    record_property("sdk_versions_before", old_versions)
    record_property("sdk_versions_after", result["owner_postcheck"]["checkpoint_migrations_checked"])
    record_property("sdk_new_versions", result["owner_postcheck"]["checkpoint_migrations_checked"] - old_versions)


def test_forged_or_expired_authority_and_actual_lost_pg_lock_stop_before_first_write(proposal, monkeypatch):
    with pytest.raises(RestoreRejected, match="SOURCE_FORWARD_OPAQUE_WITNESS_REQUIRED"):
        scopes.SourceUpgradeWitness({"target_proof_consumed": True})
    with pytest.raises(RestoreRejected, match="SOURCE_FORWARD_WITNESS_EXPIRED"):
        scopes._active(object.__new__(scopes.SourceUpgradeWitness), "authorized")
    original = forward._core

    def unlocked(witness):
        scope = scopes._active(witness, "authorized").scope
        actual = scope.owner.execute(
            "SELECT pg_advisory_unlock(hashtextextended(%s,0)) AS released", (scope.request.source.fence_key,)
        ).fetchone()
        assert actual == {"released": True}
        return original(witness)

    monkeypatch.setattr(forward, "_core", unlocked)
    with pytest.raises(forward.SourceForwardStopped, match="SOURCE_FORWARD_LIVE_PG_FENCE_REQUIRED") as stopped:
        forward.execute(proposal.request, apply_source=True)
    assert stopped.value.phase == "authorized" and prefix(proposal) == 7
    assert state(proposal.case.source) == proposal.before and materials(proposal.case) == proposal.material


def test_actual_runtime_pin_mismatch_never_reaches_source_write(proposal):
    request = replace(proposal.request, runtime_pin=replace(proposal.request.runtime_pin, saver_version="0.0"))
    request = replace(request, pin=request_pin(request))
    with pytest.raises(forward.SourceForwardStopped, match="CONTROLLER_SAVER_VERSION") as stopped:
        forward.execute(request, apply_source=True)
    assert stopped.value.phase == "source_checks"
    assert state(proposal.case.source) == proposal.before and materials(proposal.case) == proposal.material


def test_real_source_drift_after_proof_before_locked_snapshot_is_not_repaired(proposal, monkeypatch):
    original = forward._core
    changed = {}

    def drifted(witness):
        scope = scopes._active(witness, "authorized").scope
        with scope.owner.transaction():
            scope.owner.execute("SET TRANSACTION READ WRITE")
            scope.owner.execute("UPDATE mingjing_core.core_entities SET updated_at=updated_at+interval '1 second'")
            changed.update(scopes.snapshot(scope.owner))
        return original(witness)

    monkeypatch.setattr(forward, "_core", drifted)
    with pytest.raises(forward.SourceForwardStopped, match="SOURCE_FORWARD_LOCKED_CAPTURE_CHANGED") as stopped:
        forward.execute(proposal.request, apply_source=True)
    assert stopped.value.phase == "core_transaction_rejected" and prefix(proposal) == 7
    assert changed and state(proposal.case.source) == changed and changed != proposal.before
    assert materials(proposal.case) == proposal.material


def test_real_sdk_closed_owned_connection_preserves_primary_over_restore_failure(
    proposal, monkeypatch, record_property
):
    execute, checkpoint = psycopg.Connection.execute, scopes.checkpoint
    before_rows = source_rows(proposal)
    observed = {"secondary": []}

    def disconnected(connection, query, *args, **kwargs):
        try:
            result = execute(connection, query, *args, **kwargs)
        except psycopg.Error as error:
            if connection.closed:
                observed["secondary"].append(error)
            raise
        if query == "SET search_path=public" and connection.info.dbname == proposal.request.source.source.database:
            observed["closed_after_public"] = True
            connection.close()
        return result

    def actual_sdk(witness):
        try:
            return checkpoint(witness)
        except BaseException as error:
            observed["primary"] = error
            observed["sdk_frame"] = any(
                frame.tb_frame.f_code is postgres.PostgresSaver.setup.__code__
                for frame in traceback_chain(error.__traceback__)
            )
            raise

    monkeypatch.setattr(psycopg.Connection, "execute", disconnected)
    monkeypatch.setattr(scopes, "checkpoint", actual_sdk)
    with pytest.raises(forward.SourceForwardStopped, match="SOURCE_FORWARD_STAGE_FAILED") as stopped:
        forward.execute(proposal.request, apply_source=True)
    assert observed["closed_after_public"] and observed["sdk_frame"] and observed["secondary"]
    assert all(error is not observed["primary"] for error in observed["secondary"])
    assert stopped.value.phase == "checkpoint_started" and stopped.value.session_restored is False
    assert prefix(proposal) == 8 and materials(proposal.case) == proposal.material
    assert source_rows(proposal, len(before_rows["public.checkpoint_migrations"])) == before_rows
    record_property("fault", "owned-source-client-closed-after-public-before-native-sdk")
    record_property("sdk_setup_entered_before_closed_cursor_failure", observed["sdk_frame"])
    record_property("sdk_pending_ddl_executed", False)


def traceback_chain(frame):
    while frame is not None:
        yield frame
        frame = frame.tb_next


def test_after_real_core_commit_injected_boundary_error_is_unknown_and_never_reentered(proposal, monkeypatch):
    original = forward.forward_core
    calls = []

    def committed_then_boundary_error(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result)
        raise psycopg.OperationalError("synthetic-after-real-commit-boundary")

    def forbidden_checkpoint(*args, **kwargs):
        pytest.fail("UNKNOWN_CORE_BOUNDARY_MUST_NOT_CONTINUE_TO_CHECKPOINT")

    monkeypatch.setattr(forward, "forward_core", committed_then_boundary_error)
    monkeypatch.setattr(scopes, "checkpoint", forbidden_checkpoint)
    with pytest.raises(forward.SourceForwardStopped, match="SOURCE_FORWARD_STAGE_FAILED") as stopped:
        forward.execute(proposal.request, apply_source=True)
    assert len(calls) == 1 and stopped.value.phase == "core_commit_outcome_unknown"
    assert prefix(proposal) == 8 and materials(proposal.case) == proposal.material
    assert stopped.value.automatic_cleanup is False

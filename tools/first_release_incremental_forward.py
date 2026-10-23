"""Explicit synthetic-source forward stages; source privacy replay/backfill and release remain closed."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tools import first_release_incremental_scope as scope_tools
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_capture_binding import CaptureBinding
from tools.first_release_contracts import RestoreRejected, digest, ordinary, require
from tools.first_release_controller_runtime import ControllerRuntimePin, runtime_summary, verify_controller_runtime
from tools.first_release_incremental import BackupInputs, file_hash
from tools.first_release_incremental_guard import CONTROLS as GUARD_CONTROLS
from tools.first_release_incremental_guard import capture_baseline
from tools.first_release_incremental_pg import readonly, sessions
from tools.first_release_local_inputs import LocalInputs
from tools.first_release_local_restore import _proved_target
from tools.first_release_migration_steps import forward_core, grant_new_runtime, load_bundle
from tools.first_release_source_postcheck import owner_state, writer_state
from tools.first_release_target_proof import TargetProofPin

ROOT = Path(__file__).parent.parent
CONTROLS = frozenset(
    "tools/" + name
    for name in (
        "first_release_incremental_forward.py",
        "first_release_incremental_scope.py",
        "first_release_incremental_guard.py",
        "first_release_migration_steps.py",
        "first_release_source_postcheck.py",
        "first_release_source_profile.py",
        "first_release_controller_runtime.py",
        "first_release_acl.py",
    )
)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def forward_binding(
    source: BackupInputs,
    target: LocalInputs,
    capture: CaptureBinding,
    replay: CandidateReplay,
    target_pin: TargetProofPin,
    runtime_pin: ControllerRuntimePin,
) -> str:
    """Prepare an external review digest; this has no authority to mutate a source."""
    require(type(source) is BackupInputs and type(target) is LocalInputs, "SOURCE_FORWARD_TYPED_INPUTS")
    require(type(capture) is CaptureBinding and type(replay) is CandidateReplay, "SOURCE_FORWARD_TYPED_REPLAY")
    require(
        type(target_pin) is TargetProofPin and type(runtime_pin) is ControllerRuntimePin, "SOURCE_FORWARD_TYPED_PINS"
    )
    require(target_pin.validate(target, capture, replay) == source, "SOURCE_FORWARD_TARGET_SOURCE_BINDING")
    capture_baseline(source, target, capture)
    require(
        (source.release.candidate, source.release.manifest_sha256, source.python_sha256)
        == (runtime_pin.candidate, runtime_pin.manifest_sha256, runtime_pin.python_sha256)
        and dict(source.release.locks)["requirements-core.lock"] == runtime_pin.core_lock_sha256,
        "SOURCE_FORWARD_RUNTIME_BINDING",
    )
    return _digest([asdict(value) for value in (source, target, capture, replay, target_pin, runtime_pin)])


@dataclass(frozen=True)
class SourceForwardPin:
    binding_sha256: str
    controls: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> SourceForwardPin:
        require(
            type(value) is dict
            and set(value) == {"schema", "binding_sha256", "controls"}
            and value["schema"] == "first-release-local-source-forward-pin-v1"
            and type(value["controls"]) is dict,
            "SOURCE_FORWARD_PIN_FIELDS",
        )
        return cls(value["binding_sha256"], tuple(sorted(value["controls"].items())))

    def validate(self, request: ForwardInputs) -> None:
        require(digest(self.binding_sha256), "SOURCE_FORWARD_BINDING_DIGEST")
        require(
            type(self.controls) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.controls)
            and len(self.controls) == len(CONTROLS)
            and set(dict(self.controls)) == CONTROLS,
            "SOURCE_FORWARD_CONTROL_SET",
        )
        for name, expected in self.controls:
            ordinary(ROOT / name)
            require(digest(expected) and file_hash(ROOT / name) == expected, "SOURCE_FORWARD_CONTROL_CHANGED")
        require(
            forward_binding(
                request.source, request.target, request.capture, request.replay, request.target_pin, request.runtime_pin
            )
            == self.binding_sha256,
            "SOURCE_FORWARD_REVIEWED_INPUT_CHANGED",
        )


@dataclass(frozen=True)
class ForwardInputs:
    source: BackupInputs
    target: LocalInputs
    capture: CaptureBinding
    replay: CandidateReplay
    target_pin: TargetProofPin
    runtime_pin: ControllerRuntimePin
    pin: SourceForwardPin
    environment: Mapping[str, str] | None = field(default=None, repr=False, compare=False)

    def validate(self) -> dict[str, Any]:
        require(type(self.pin) is SourceForwardPin, "SOURCE_FORWARD_TYPED_REVIEW_PIN")
        self.pin.validate(self)
        return capture_baseline(self.source, self.target, self.capture)

    def guard_controls(self) -> tuple[tuple[str, str], ...]:
        controls = dict(self.pin.controls)
        return tuple(sorted((name, controls["tools/" + name]) for name in GUARD_CONTROLS))


class SourceForwardStopped(RestoreRejected):
    def __init__(self, code: str, phase: str, *, session_restored: bool = True) -> None:
        safe = code if re.fullmatch(r"[A-Z][A-Z0-9_]*", code) else "SOURCE_FORWARD_REJECTED"
        super().__init__(safe)
        self.phase = phase
        self.session_restored = session_restored
        self.automatic_cleanup = False


def _owner_postcheck(scope: Any, *, saver_count: int | None) -> dict[str, Any]:
    with scope.owner.transaction():
        scope.owner.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        scope.owner.execute("SET LOCAL search_path=pg_catalog")
        return owner_state(
            scope.owner,
            scope.request.source,
            scope.baseline,
            scope.checkpoint_versions,
            saver_count=saver_count,
            allowed_pids={scope.pid},
        )


def _writer_postcheck(scope: Any) -> dict[str, Any]:
    with (
        psycopg.connect(readonly(scope.dsns["writer"]), autocommit=True, row_factory=dict_row) as writer,
        writer.transaction(),
    ):
        writer.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        writer.execute("SET LOCAL search_path=pg_catalog")
        allowed = {scope.pid, writer.info.backend_pid}
        sessions(scope.owner, allowed)
        result = writer_state(writer, scope.request.source, allowed_pids=allowed)
        sessions(scope.owner, allowed)
    sessions(scope.owner, {scope.pid})
    return result


def _core(witness: scope_tools.SourceUpgradeWitness) -> list[int]:
    authority = scope_tools._active(witness, "authorized")
    scope = authority.scope
    bundle = load_bundle(scope.request.source.release, scope.request.source.candidate_source)
    scope.phase = "core_transaction_started"
    try:
        applied = forward_core(
            scope.owner,
            bundle,
            scope.request.source.source.migrations,
            prepare_locked_source=lambda connection: scope_tools.prepare_locked_source(witness, connection),
        )
    except RestoreRejected as error:
        scope.phase = (
            "core_commit_outcome_unknown"
            if str(error) == "FORWARD_CORE_TRANSACTION_FAILED"
            else "core_transaction_rejected"
        )
        raise
    except psycopg.Error:
        scope.phase = "core_commit_outcome_unknown"
        raise
    scope.phase = "core_committed"
    _owner_postcheck(scope, saver_count=None)
    scope.phase = "core_verified"
    return applied


def _stages(witness: scope_tools.SourceUpgradeWitness) -> dict[str, Any]:
    scope = scope_tools._active(witness, "authorized").scope
    applied = _core(witness)
    count = scope_tools.checkpoint(witness)
    _owner_postcheck(scope, saver_count=count)
    scope_tools.pregrant_original_acl(witness)
    _grant(scope)
    owner = _owner_postcheck(scope, saver_count=count)
    writer = _writer_postcheck(scope)
    scope_tools._materials(scope)
    scope.phase = "source_forward_completed"
    return {"forward_migrations": applied, "owner_postcheck": owner, "writer_postcheck": writer}


def _grant(scope: Any) -> None:
    scope.phase = "grant_started"
    try:
        with scope.owner.transaction():
            scope.owner.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, READ WRITE")
            grant_new_runtime(scope.owner, scope.request.source.source.database + "_writer")
    except psycopg.Error:
        scope.phase = "grant_commit_outcome_unknown"
        raise
    except RestoreRejected:
        scope.phase = "grant_rolled_back"
        raise
    scope.phase = "grant_committed"


def _apply(scope: Any) -> dict[str, Any]:
    from langgraph.checkpoint.postgres import PostgresSaver

    request = scope.request
    runtime = verify_controller_runtime(request.source, request.replay, request.runtime_pin, PostgresSaver)
    failure: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        with _proved_target(
            request.target,
            apply_local=True,
            upgrade_local=True,
            capture_binding=request.capture,
            withdrawals_replay=request.replay,
            target_proof_pin=request.target_pin,
            environment=request.environment,
        ) as proof:
            try:
                with scope_tools._authorized(scope, proof, runtime) as witness:
                    result = _stages(witness)
                    result["target_proof"] = dict(
                        scope_tools._active(witness, "source_forward_completed").target_summary
                    )
                    result["controller_runtime"] = runtime_summary(runtime)
            except BaseException as error:
                failure = scope_tools._prefer_failure(failure, error)
    except BaseException as error:
        failure = scope_tools._prefer_failure(failure, error)
    if failure is not None:
        raise failure
    require(result is not None, "SOURCE_FORWARD_RESULT_REQUIRED")
    return result


def _receipt(request: ForwardInputs) -> dict[str, Any]:
    return {
        "schema": "first-release-local-source-forward-v1",
        "candidate": request.source.release.candidate,
        "source_operation_id": request.source.operation_id,
        "source_database_oid": request.source.source.database_oid,
        "source_forward_completed": False,
        "source_upgraded": False,
        "source_write_authorized": False,
        "privacy_replay_pending": True,
        "backfill_pending": True,
        "source_restore_content_verified": False,
        "native_restore_completed": False,
        "runtime_verified": False,
        "central_binding_verified": False,
        "global_quiescence_verified": False,
        "linux_attestation": False,
        "publication": False,
        "database_connections": 0,
        "processes": 0,
        "file_writes": 0,
        "model_calls": 0,
        "external_sends": 0,
    }


def execute(request: ForwardInputs, *, apply_source: bool = False) -> dict[str, Any]:
    require(type(request) is ForwardInputs and type(apply_source) is bool, "SOURCE_FORWARD_TYPED_REQUEST")
    baseline = request.validate()
    receipt = _receipt(request)
    if not apply_source:
        return receipt
    scope = None
    failure: BaseException | None = None
    result: dict[str, Any] | None = None
    try:
        with scope_tools._held_forward(request, baseline) as scope:
            try:
                result = _apply(scope)
            except BaseException as error:
                failure = scope_tools._prefer_failure(failure, error)
    except BaseException as error:
        failure = scope_tools._prefer_failure(failure, error)
    if failure is not None:
        phase = "source_checks" if scope is None else scope.phase
        restored = scope is None or scope.session_restored
        if isinstance(failure, (KeyboardInterrupt, SystemExit, GeneratorExit)):
            raise failure
        code = str(failure) if isinstance(failure, RestoreRejected) else "SOURCE_FORWARD_STAGE_FAILED"
        raise SourceForwardStopped(code, phase, session_restored=restored) from None
    for name in ("database_connections", "processes", "file_writes"):
        receipt.pop(name)
    require(result is not None and scope is not None, "SOURCE_FORWARD_RESULT_REQUIRED")
    return dict(receipt, **result, phase=scope.phase, source_forward_completed=True, maintenance_retained=True)

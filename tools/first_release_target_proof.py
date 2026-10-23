"""One-use in-process local target proof; never a source-write or publication authorization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools.first_release_acl import QUOTA, verify_database_acl
from tools.first_release_candidate_process import CandidateReplay
from tools.first_release_capture_binding import CaptureBinding
from tools.first_release_contracts import RestoreRejected, digest, ordinary, require
from tools.first_release_incremental import BackupInputs
from tools.first_release_incremental_pg import snapshot
from tools.first_release_local_inputs import LocalInputs, file_hash
from tools.first_release_local_pg import _birth_identity, server_identity
from tools.first_release_local_upgrade import _require_creator
from tools.first_release_source_profile import triggers

ROOT = Path(__file__).parent.parent
CONTROLS = frozenset(
    "tools/" + name
    for name in (
        "first_release_target_proof.py",
        "first_release_local_restore.py",
        "first_release_local_pg.py",
        "first_release_local_inputs.py",
        "first_release_local_upgrade.py",
        "first_release_acl.py",
        "first_release_capture_binding.py",
        "first_release_candidate_process.py",
        "first_release_source_profile.py",
        "first_release_contracts.py",
        "first_release_source.py",
        "first_release_restore.py",
        "core_incremental_contracts.py",
        "b1_restore_proof_worker.py",
        "b1_restore_replay_contracts.py",
    )
) | frozenset({"mingjing_core/repositories/foundation.py", "mingjing_core/repositories/permissions.py"})
_SEAL = object()


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def target_binding(inputs: LocalInputs, capture: CaptureBinding, replay: CandidateReplay) -> str:
    """Read-only preparation of external reviewed inputs; this hash alone cannot mint a proof."""
    require(
        type(inputs) is LocalInputs and type(capture) is CaptureBinding and type(replay) is CandidateReplay,
        "TARGET_PROOF_TYPED_INPUTS_REQUIRED",
    )
    inputs.validate()
    source, _ = capture.validate(inputs)
    replay.validate(inputs)
    pin = dict(replay.preflight.pin)
    require(
        replay.preflight.python == source.python
        and pin["python_sha256"] == source.python_sha256
        and pin["ledger_sha256"] == capture.pin.ledger_sha256,
        "TARGET_PROOF_CAPTURE_REPLAY_BINDING",
    )
    return _digest(dict(local=asdict(inputs), capture=asdict(capture), replay=asdict(replay), source=asdict(source)))


@dataclass(frozen=True)
class TargetProofPin:
    binding_sha256: str
    controls: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> TargetProofPin:
        require(
            isinstance(value, dict)
            and set(value) == {"schema", "binding_sha256", "controls"}
            and value["schema"] == "first-release-local-target-proof-pin-v1"
            and isinstance(value["controls"], dict),
            "TARGET_PROOF_PIN_FIELDS",
        )
        return cls(value["binding_sha256"], tuple(sorted(value["controls"].items())))

    def validate(self, inputs: LocalInputs, capture: CaptureBinding, replay: CandidateReplay) -> BackupInputs:
        require(digest(self.binding_sha256), "TARGET_PROOF_BINDING_DIGEST")
        require(
            type(self.controls) is tuple
            and all(type(item) is tuple and len(item) == 2 for item in self.controls)
            and len(self.controls) == len(CONTROLS)
            and set(dict(self.controls)) == CONTROLS,
            "TARGET_PROOF_REVIEWED_CONTROLS",
        )
        for name, expected in self.controls:
            ordinary(ROOT / name)
            require(digest(expected) and file_hash(ROOT / name) == expected, "TARGET_PROOF_CONTROLLER_CHANGED")
        require(target_binding(inputs, capture, replay) == self.binding_sha256, "TARGET_PROOF_INPUT_CHANGED")
        source, _ = capture.validate(inputs)
        return source


class TargetProof:
    __slots__ = ()

    def __new__(cls, seal: object = None):
        require(cls is TargetProof and seal is _SEAL, "TARGET_PROOF_NOT_CONSTRUCTIBLE")
        return object.__new__(cls)

    def __repr__(self) -> str:
        return "<TargetProof>"

    def __reduce__(self) -> Any:
        raise RestoreRejected("TARGET_PROOF_NOT_SERIALIZABLE")


@dataclass(frozen=True)
class _Record:
    inputs: LocalInputs
    capture: CaptureBinding
    replay: CandidateReplay
    pin: TargetProofPin
    source_digest: str
    birth: tuple[int, int, int]
    state_digest: str
    creator: Any = field(repr=False)
    dsns: dict[str, str] = field(repr=False)


_PROOFS: dict[TargetProof, _Record] = {}


def _current_birth(
    inputs: LocalInputs, source: BackupInputs, dsns: dict[str, str], creator: Any
) -> tuple[int, int, int]:
    _require_creator(inputs, dsns, creator)
    birth = _birth_identity(inputs, creator)
    actual = creator.execute(
        "SELECT d.oid,d.datdba,(SELECT oid FROM pg_roles WHERE rolname=%s) AS writer_oid,"
        "(pg_control_system()).system_identifier::text AS system_identifier "
        "FROM pg_database d WHERE d.datname=%s",
        (inputs.contract.database + "_writer", inputs.contract.database),
    ).fetchone()
    require(
        actual
        and (actual["oid"], actual["datdba"], actual["writer_oid"])
        == (birth.database_oid, birth.owner_oid, birth.writer_oid)
        and actual["system_identifier"] == source.source.system_identifier
        and actual["oid"] != source.source.database_oid,
        "TARGET_PROOF_CREATED_IDENTITY_CHANGED",
    )
    return birth.database_oid, birth.owner_oid, birth.writer_oid


def _final_state(inputs: LocalInputs, source: BackupInputs, dsns: dict[str, str], birth: tuple[int, int, int]) -> str:
    with (
        psycopg.connect(dsns["owner"], autocommit=True, row_factory=dict_row) as c,
        c.transaction(),
    ):
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        c.execute("SET LOCAL search_path=pg_catalog")
        server_identity(c, conninfo_to_dict(dsns["owner"]))
        actual = c.execute(
            "SELECT oid,datdba,(SELECT oid FROM pg_roles WHERE rolname=current_user) AS role_oid "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        require(
            actual and (actual["oid"], actual["datdba"], actual["role_oid"]) == (birth[0], birth[1], birth[1]),
            "TARGET_PROOF_OWNER_IDENTITY",
        )
        owners = sorted(row["id"] for row in c.execute("SELECT id FROM mingjing_core.core_owners"))
        require(owners == list(source.source.owners), "TARGET_PROOF_OWNER_SET")
        history = {
            str(row["version"]): row["checksum"]
            for row in c.execute("SELECT version,checksum FROM mingjing_core.schema_migrations")
        }
        require(history == dict(inputs.release.migrations), "TARGET_PROOF_HISTORY_1_8")
        triggers(c, 7)
        busy = c.execute(
            "SELECT EXISTS(SELECT 1 FROM mingjing_core.core_runs WHERE status IN ('queued','running') "
            "OR lease_until>clock_timestamp()) OR EXISTS(SELECT 1 FROM pg_stat_activity "
            "WHERE datid=(SELECT oid FROM pg_database WHERE datname=current_database()) "
            "AND pid<>pg_backend_pid()) AS busy"
        ).fetchone()["busy"]
        require(not busy, "TARGET_PROOF_ACTIVE_OR_OTHER_SESSION")
        for name in QUOTA:
            require(
                not c.execute(
                    sql.SQL("SELECT EXISTS(SELECT 1 FROM {}) AS occupied").format(sql.Identifier(*name.split(".")))
                ).fetchone()["occupied"],
                "TARGET_PROOF_CENTRAL_NOT_EMPTY",
            )
        sequence = c.execute(
            "SELECT last_value,log_cnt,is_called FROM mingjing_core.core_model_usage_id_seq"
        ).fetchone()
        require(sequence == {"last_value": 1, "log_cnt": 0, "is_called": False}, "TARGET_PROOF_CENTRAL_SEQUENCE_USED")
        return _digest(snapshot(c))


def _check_target(inputs: LocalInputs, source: BackupInputs, dsns: dict[str, str], creator: Any) -> tuple[Any, str]:
    try:
        birth = _current_birth(inputs, source, dsns, creator)
        verify_database_acl(
            inputs.contract,
            inputs.release,
            environment={"FIRST_RELEASE_" + role.upper() + "_DSN": dsns[role] for role in ("owner", "writer")},
        )
        state = _final_state(inputs, source, dsns, birth)
        require(_current_birth(inputs, source, dsns, creator) == birth, "TARGET_PROOF_CREATED_IDENTITY_CHANGED")
    except psycopg.Error:
        raise RestoreRejected("TARGET_PROOF_FINAL_DATABASE_CHECK_FAILED") from None
    return birth, state


@contextmanager
def _held_proof(
    inputs: LocalInputs,
    capture: CaptureBinding,
    replay: CandidateReplay,
    pin: TargetProofPin,
    dsns: dict[str, str],
    creator: Any,
) -> Iterator[TargetProof]:
    require(type(pin) is TargetProofPin, "TARGET_PROOF_REVIEW_PIN_REQUIRED")
    source = pin.validate(inputs, capture, replay)
    # The earlier upgrade ACL check precedes replay, so it cannot authorize this mint.
    birth, state = _check_target(inputs, source, dsns, creator)
    require(pin.validate(inputs, capture, replay) == source, "TARGET_PROOF_INPUT_CHANGED")
    proof = TargetProof(_SEAL)
    _PROOFS[proof] = _Record(inputs, capture, replay, pin, _digest(asdict(source)), birth, state, creator, dict(dsns))
    try:
        yield proof
    finally:
        _PROOFS.pop(proof, None)


def consume_target_proof(proof: TargetProof, *, source: BackupInputs) -> dict[str, Any]:
    require(type(proof) is TargetProof, "TARGET_PROOF_OPAQUE_INSTANCE_REQUIRED")
    record = _PROOFS.pop(proof, None)
    require(record is not None, "TARGET_PROOF_EXPIRED_OR_CONSUMED")
    require(
        type(source) is BackupInputs and _digest(asdict(source)) == record.source_digest, "TARGET_PROOF_SOURCE_BINDING"
    )
    current = record.pin.validate(record.inputs, record.capture, record.replay)
    require(current == source, "TARGET_PROOF_SOURCE_BINDING")
    birth, state = _check_target(record.inputs, source, record.dsns, record.creator)
    require(birth == record.birth, "TARGET_PROOF_CREATED_IDENTITY_CHANGED")
    require(state == record.state_digest, "TARGET_PROOF_TARGET_STATE_CHANGED")
    require(record.pin.validate(record.inputs, record.capture, record.replay) == source, "TARGET_PROOF_INPUT_CHANGED")
    return {
        "schema": "first-release-local-target-proof-consumed-v1",
        "target_proof_consumed": True,
        "source_operation_id": source.operation_id,
        "target_operation_id": record.inputs.contract.operation_id,
        "target_database_oid": record.birth[0],
        "binding_sha256": record.pin.binding_sha256,
        "target_state_sha256": state,
        "source_write_authorized": False,
        "controller_runtime_verified": False,
        "source_restore_content_verified": False,
        "native_restore_completed": False,
        "runtime_verified": False,
        "central_binding_verified": False,
        "linux_attestation": False,
        "publication": False,
        "target_database_connections": 16,
        "final_target_database_connections": 6,
        "global_quiescence_verified": False,
    }

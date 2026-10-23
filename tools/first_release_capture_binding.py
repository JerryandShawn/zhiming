"""Reviewed local capture to fresh original-restore binding; no formal restore authority."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools.first_release_contracts import digest, ordinary, read_json, require
from tools.first_release_incremental import HERE, BackupInputs, file_hash
from tools.first_release_local_inputs import LocalInputs

CONTROLS = frozenset(
    {
        "first_release_capture_binding.py",
        "first_release_local_restore.py",
        "first_release_local_pg.py",
        "first_release_local_upgrade.py",
    }
)
PROJECTION = "postgres-jsonb-utc-v1"


@dataclass(frozen=True)
class CaptureBindingPin:
    candidate: str
    manifest_sha256: str
    capture_inputs_sha256: str
    capture_receipt_sha256: str
    source_state_sha256: str
    dump_sha256: str
    ledger_sha256: str
    target_operation_id: str
    controls: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> CaptureBindingPin:
        fields = set(cls.__dataclass_fields__)
        require(isinstance(value, dict) and set(value) == fields | {"schema"}, "CAPTURE_PIN_FIELDS")
        require(value["schema"] == "first-release-local-capture-binding-pin-v1", "CAPTURE_PIN_SCHEMA")
        require(isinstance(value["controls"], dict), "CAPTURE_PIN_CONTROLS")
        return cls(
            **{key: value[key] for key in fields - {"controls"}},
            controls=tuple(sorted(value["controls"].items())),
        )

    def validate(self, inputs: LocalInputs) -> None:
        require(
            self.candidate == inputs.release.candidate and self.manifest_sha256 == inputs.release.manifest_sha256,
            "CAPTURE_CANDIDATE_BINDING",
        )
        require(self.target_operation_id == inputs.contract.operation_id, "CAPTURE_TARGET_OPERATION_BINDING")
        require(
            all(digest(getattr(self, name)) for name in self.__dataclass_fields__ if name.endswith("sha256")),
            "CAPTURE_PIN_DIGEST",
        )
        require(
            type(self.controls) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.controls)
            and len(self.controls) == len(CONTROLS)
            and set(dict(self.controls)) == CONTROLS,
            "CAPTURE_REVIEWED_CONTROLS",
        )
        for name, expected in self.controls:
            ordinary(HERE / name)
            require(digest(expected) and file_hash(HERE / name) == expected, "CAPTURE_CONSUMER_CHANGED")


def state_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def checked_state(receipt: dict[str, Any]) -> dict[str, Any]:
    require(receipt.get("source_projection") == PROJECTION, "CAPTURE_EXPLICIT_UTC_PROJECTION_REQUIRED")
    snapshots = receipt.get("source_snapshots")
    require(
        isinstance(snapshots, dict)
        and set(snapshots) == {"before", "after"}
        and snapshots["before"] == snapshots["after"],
        "CAPTURE_BEFORE_AFTER_REQUIRED",
    )
    state = snapshots["before"]
    require(isinstance(state, dict) and set(state) == {"tables", "sequences", "columns"}, "CAPTURE_COMPLETE_STATE")
    require(all(isinstance(values, dict) for values in state.values()), "CAPTURE_STATE_MAPS")
    tables, sequences, columns = state["tables"], state["sequences"], state["columns"]
    require(tables and set(columns) == set(tables) and not set(tables) & set(sequences), "CAPTURE_RELATION_SET")
    require(
        all(re.fullmatch(r"(?:mingjing_core|public)\.[A-Za-z_][A-Za-z0-9_]*", name) for name in (*tables, *sequences)),
        "CAPTURE_RELATION_NAMES",
    )
    require(all(digest(value) for value in tables.values()), "CAPTURE_TABLE_HASHES")
    for values in columns.values():
        require(isinstance(values, list) and values, "CAPTURE_COLUMN_SET")
        require(
            all(
                isinstance(row, dict)
                and set(row) == {"name", "type", "not_null"}
                and isinstance(row["name"], str)
                and row["name"]
                and isinstance(row["type"], str)
                and row["type"]
                and type(row["not_null"]) is bool
                for row in values
            )
            and len({row["name"] for row in values}) == len(values),
            "CAPTURE_COLUMN_FIELDS",
        )
    for value in sequences.values():
        require(
            isinstance(value, dict)
            and set(value) == {"last_value", "log_cnt", "is_called"}
            and type(value["last_value"]) is int
            and type(value["log_cnt"]) is int
            and type(value["is_called"]) is bool,
            "CAPTURE_SEQUENCE_FIELDS",
        )
    return state


def receipt_binding(receipt: dict[str, Any], source: BackupInputs, pin: CaptureBindingPin) -> dict[str, Any]:
    from tools.first_release_incremental_pg import capture_lineage

    require(
        receipt.get("schema") == "first-release-local-incremental-backup-v1"
        and receipt.get("candidate") == pin.candidate
        and receipt.get("capture_lineage") == capture_lineage(source),
        "CAPTURE_ACTUAL_LINEAGE_BINDING",
    )
    expected = {
        "status": "local_backup_captured",
        "backup_captured": True,
        "session_checks": "before_after",
        "same_mvcc_snapshot": True,
        "sequence_before_after_checked": True,
        "global_quiescence_verified": False,
        "maintenance_retained": True,
        "source_upgraded": False,
        "source_restore_content_verified": False,
        "native_restore_completed": False,
        "runtime_verified": False,
        "central_binding_verified": False,
        "linux_attestation": False,
        "publication": False,
        "model_calls": 0,
        "external_sends": 0,
    }
    require(
        all(type(receipt.get(key)) is type(value) and receipt[key] == value for key, value in expected.items()),
        "CAPTURE_BOUNDED_RECEIPT",
    )
    state = checked_state(receipt)
    require(
        state_digest(state) == receipt.get("source_state_sha256") == pin.source_state_sha256
        and receipt.get("dump_sha256") == pin.dump_sha256
        and receipt.get("ledger_sha256") == pin.ledger_sha256,
        "CAPTURE_REVIEWED_STATE_BINDING",
    )
    return state


@dataclass(frozen=True)
class CaptureBinding:
    capture_inputs: Path
    pin: CaptureBindingPin

    @classmethod
    def parse(cls, capture_inputs: Path, pin: dict[str, Any]) -> CaptureBinding:
        return cls(capture_inputs, CaptureBindingPin.parse(pin))

    def validate(self, inputs: LocalInputs) -> tuple[BackupInputs, dict[str, Any]]:
        require(inputs.contract.local_drill is True, "CAPTURE_LOCAL_ONLY_NO_FORMAL")
        require(type(self.pin) is CaptureBindingPin, "CAPTURE_TYPED_PIN_REQUIRED")
        self.pin.validate(inputs)
        ordinary(self.capture_inputs)
        require(file_hash(self.capture_inputs) == self.pin.capture_inputs_sha256, "CAPTURE_INPUT_CHANGED")
        source = BackupInputs.parse(read_json(self.capture_inputs), inputs.workspace)
        require(
            self.capture_inputs == source.operation_dir / "capture-inputs.json"
            and source.operation_id != inputs.contract.operation_id,
            "CAPTURE_FIXED_DISTINCT_OPERATION_PATH",
        )
        source.validate()
        require(
            source.release.candidate == inputs.release.candidate
            and source.release.manifest_sha256 == inputs.release.manifest_sha256
            and dict(source.release.locks) == dict(inputs.release.locks)
            and dict(source.source.migrations) == dict(inputs.dump_pin.source_migrations),
            "CAPTURE_SOURCE_CANDIDATE_PREFIX_BINDING",
        )
        for name, expected in (
            ("backup.dump", self.pin.dump_sha256),
            ("latest-withdrawals.json", self.pin.ledger_sha256),
            ("backup-receipt.json", self.pin.capture_receipt_sha256),
        ):
            path = source.operation_dir / name
            ordinary(path)
            require(file_hash(path) == expected, "CAPTURE_ARTIFACT_CHANGED")
        require(
            self.pin.dump_sha256 == inputs.dump_pin.dump_sha256 == file_hash(inputs.dump),
            "CAPTURE_TARGET_DUMP_BINDING",
        )
        receipt = read_json(source.operation_dir / "backup-receipt.json")
        return source, receipt_binding(receipt, source, self.pin)


def target_state(inputs: LocalInputs, dsns: dict[str, str], creator: Any, source: BackupInputs) -> dict[str, Any]:
    from tools.first_release_incremental_pg import readonly, snapshot
    from tools.first_release_local_pg import server_identity
    from tools.first_release_local_upgrade import _require_creator

    _require_creator(inputs, dsns, creator)
    owner_dsn = dsns["owner"]
    fields = conninfo_to_dict(owner_dsn)
    with (
        psycopg.connect(readonly(owner_dsn), autocommit=True, row_factory=dict_row) as connection,
        connection.transaction(),
    ):
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        server_identity(connection, fields)
        actual = connection.execute(
            "SELECT oid,datdba,(SELECT oid FROM pg_roles WHERE rolname=current_user) AS role_oid "
            "FROM pg_database WHERE datname=current_database()"
        ).fetchone()
        known = creator.execute(
            "SELECT oid,datdba FROM pg_database WHERE datname=%s", (inputs.contract.database,)
        ).fetchone()
        require(
            actual
            and known
            and actual["oid"] == known["oid"]
            and actual["datdba"] == actual["role_oid"] == known["datdba"],
            "CAPTURE_FRESH_TARGET_IDENTITY",
        )
        owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
        require(owners == list(source.source.owners), "CAPTURE_RESTORED_OWNER_SET")
        rows = connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
        require(
            {str(row["version"]): row["checksum"] for row in rows} == dict(source.source.migrations),
            "CAPTURE_RESTORED_ORIGINAL_PREFIX",
        )
        objects = connection.execute(
            "SELECT n.nspname||'.'||c.relname AS name,c.relkind,c.relowner FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public') "
            "AND c.relkind IN ('r','p','S','v','m','f')"
        ).fetchall()
        require(
            all(row["relowner"] == actual["role_oid"] and row["relkind"] in {"r", "S"} for row in objects),
            "CAPTURE_RESTORED_RELATION_PROFILE",
        )
        result = snapshot(connection)
        require(
            {row["name"] for row in objects} == set(result["tables"]) | set(result["sequences"]),
            "CAPTURE_RESTORED_EXTRA_RELATION",
        )
    return result


def verify_capture_binding(
    request: CaptureBinding, inputs: LocalInputs, dsns: dict[str, str], creator: Any
) -> dict[str, Any]:
    source, before = request.validate(inputs)
    restored = target_state(inputs, dsns, creator, source)
    require(before["columns"] == restored["columns"], "CAPTURE_RESTORED_COLUMNS_DIFFER")
    require(before["tables"] == restored["tables"], "CAPTURE_RESTORED_TABLE_FIELDS_DIFFER")
    require(set(before["sequences"]) == set(restored["sequences"]), "CAPTURE_RESTORED_SEQUENCE_SET_DIFFER")
    require(
        all(
            all(values[key] == restored["sequences"][name][key] for key in ("last_value", "is_called"))
            for name, values in before["sequences"].items()
        ),
        "CAPTURE_RESTORED_SEQUENCE_SEMANTICS_DIFFER",
    )
    request.validate(inputs)
    return {
        "schema": "first-release-local-capture-binding-v1",
        "candidate": inputs.release.candidate,
        "source_operation_id": source.operation_id,
        "target_operation_id": inputs.contract.operation_id,
        "source_state_sha256": request.pin.source_state_sha256,
        "restored_state_sha256": state_digest(restored),
        "source_projection": PROJECTION,
        "tables_checked": len(restored["tables"]),
        "sequences_checked": len(restored["sequences"]),
        "sequence_log_cnt_cross_restore_equality_required": False,
        "local_capture_binding_verified": True,
        "local_original_content_verified": True,
        "source_restore_content_verified": False,
        "native_restore_completed": False,
        "runtime_verified": False,
        "central_binding_verified": False,
        "linux_attestation": False,
        "publication": False,
        "database_connections": 1,
    }

"""Fail-closed inputs for a quiesced Core PG upgrade, separate from first install."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

TARGET = "b9a89b6f84f7bebb640de080548010859aae630c"
EXPECTED_MANIFEST = "49038f8c0dc6bb293ba688af91018cbe6339b319c388d290fd000a256e36b33c"
PREVIOUS = "7dbc951eaffebd3d812169865eaefcde16a00ed9"
RELEASE_ROOT = "/root/zhiming-core-releases"
MODEL_BASE = "https://api.kimi.com/coding/v1"
MIGRATIONS = {
    "1": "0015f6b2a9d655b5d47774a7fc44456a299953db1b0b05fcd13558206f855586",
    "2": "a7df7398ce522df386dbefcf464b7d0b550fabd558e47adec6fd991c15715f67",
    "3": "9905263b6a5bb7eabd133607b587efc055c475ea6017c497116be02df6d32ff5",
    "4": "eb6f19a7753168387388cff5d001694f90676dcbc60a72c5d7de8ccb76f27145",
    "5": "19182ec61c19d9ff3472a867b9b2ce41fa60fe22579e83dd04b4a50308708e62",
    "6": "c3469b6bad49358c11562ec16c70f840d5a0d50a8c9041c2f044a888aa644ee2",
    "7": "6c6c544a9b3def93da445ff5a58338e242c096294627dd7414c139263e3083ce",
}
LIVE_UNITS = (
    "mingjingtai.service",
    "zhiming-core-feishu.service",
    "zhiming-core-reports.service",
    "zhiming-core-reports.timer",
)
STAGE_UNITS = ("mingjingtai-stage.service", "zhiming-core-stage.service")
SHA = re.compile(r"[0-9a-f]{64}")


class UpgradeRejected(RuntimeError):
    """Only a public error code crosses the CLI boundary."""


def require(condition: object, code: str) -> None:
    if not condition:
        raise UpgradeRejected(code)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class Request:
    operation_id: str
    scope: str
    hostname: str
    manifest_sha256: str
    controller_sha256: str
    owners: tuple[str, ...]
    minimum_free_bytes: int
    unit_sha256: Mapping[str, str]
    skill_manifest_sha256: str

    @property
    def database(self) -> str:
        return f"zhiming_core_{self.scope}"

    @property
    def units(self) -> tuple[str, ...]:
        return LIVE_UNITS if self.scope == "live" else STAGE_UNITS

    @property
    def release(self) -> str:
        return str(PurePosixPath(RELEASE_ROOT) / TARGET)

    @property
    def restore_database(self) -> str:
        return "zhiming_core_b1_restore" if self.scope == "stage" else "zhiming_core_live_b1_restore"

    @classmethod
    def parse(cls, value: dict[str, Any]) -> Request:
        require(
            set(value)
            <= {
                "schema",
                "operation_id",
                "scope",
                "hostname",
                "target",
                "previous",
                "manifest_sha256",
                "controller_sha256",
                "owners",
                "minimum_free_bytes",
                "unit_sha256",
                "skill_manifest_sha256",
                "host_config_sha256",
            },
            "UNKNOWN_REQUEST_FIELD",
        )
        require(value.get("schema") == "b1-incremental-request-v1", "REQUEST_SCHEMA")
        require(value.get("target") == TARGET and value.get("previous") == PREVIOUS, "PINNED_CANDIDATE")
        require(value.get("scope") in {"stage", "live"}, "TARGET_SCOPE")
        require(re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", str(value.get("operation_id", ""))), "OPERATION_ID")
        require(re.fullmatch(r"[a-zA-Z0-9.-]{1,200}", str(value.get("hostname", ""))), "HOST_IDENTITY")
        for key in ("manifest_sha256", "controller_sha256"):
            require(isinstance(value.get(key), str) and SHA.fullmatch(value[key]), "REQUEST_HASH")
        require(value["manifest_sha256"] == EXPECTED_MANIFEST, "PINNED_RELEASE_MANIFEST")
        owners = value.get("owners")
        require(isinstance(owners, list) and owners, "EXPLICIT_OWNERS")
        require(
            all(isinstance(owner, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", owner) for owner in owners),
            "OWNER",
        )
        require(len(owners) == len(set(owners)), "DUPLICATE_OWNER")
        minimum = value.get("minimum_free_bytes")
        require(type(minimum) is int and minimum >= 8 * 1024**3, "CAPACITY_BUDGET")
        units = LIVE_UNITS if value["scope"] == "live" else STAGE_UNITS
        hashes = value.get("unit_sha256")
        require(isinstance(hashes, dict) and set(hashes) == set(units), "EXACT_WRITER_UNITS")
        require(
            all(
                isinstance(item, str) and (SHA.fullmatch(item) or value["scope"] == "stage" and item == "absent")
                for item in hashes.values()
            ),
            "UNIT_HASH",
        )
        skill = value.get("skill_manifest_sha256", "")
        require(value["scope"] != "live" or isinstance(skill, str) and SHA.fullmatch(skill), "HERMES_MANIFEST_HASH")
        return cls(
            value["operation_id"],
            value["scope"],
            value["hostname"],
            value["manifest_sha256"],
            value["controller_sha256"],
            tuple(owners),
            minimum,
            dict(hashes),
            skill,
        )


def authorize(raw: dict[str, Any], approval: dict[str, Any], controller: str, now: datetime) -> Request:
    request = Request.parse(raw)
    require(
        set(approval)
        <= {
            "schema",
            "operation_id",
            "scope",
            "request_sha256",
            "controller_sha256",
            "expires_at",
            "quiesced_upgrade",
            "resume_business",
            "model_calls",
            "channel_sends",
            "restore_sha256",
            "migration_sha256",
            "backfill_review_sha256",
        },
        "UNKNOWN_APPROVAL_FIELD",
    )
    require(approval.get("schema") == "b1-incremental-approval-v1", "APPROVAL_SCHEMA")
    require(approval.get("request_sha256") == digest(raw), "APPROVAL_REQUEST_HASH")
    require(approval.get("controller_sha256") == request.controller_sha256 == controller, "CONTROLLER_HASH")
    require(approval.get("operation_id") == request.operation_id, "APPROVAL_OPERATION")
    require(approval.get("scope") == request.scope and approval.get("quiesced_upgrade") is True, "EXPLICIT_SCOPE")
    require(
        all(approval.get(key) is False for key in ("resume_business", "model_calls", "channel_sends")),
        "NO_EFFECTS",
    )
    try:
        expires = datetime.fromisoformat(approval["expires_at"])
        require(now.utcoffset() is not None and expires.utcoffset() is not None and now < expires, "APPROVAL_EXPIRED")
    except (KeyError, TypeError, ValueError):
        raise UpgradeRejected("APPROVAL_TIME") from None
    return request


def validate_snapshot(request: Request, value: dict[str, Any], *, migrated: bool) -> None:
    require(value.get("hostname") == request.hostname, "HOST_IDENTITY")
    require(value.get("manifest_sha256") == request.manifest_sha256, "RELEASE_MANIFEST")
    require(value.get("source_verified") is True and value.get("target") == TARGET, "RELEASE_SOURCE")
    require(value.get("migration_manifest") == MIGRATIONS, "PACKAGE_MIGRATIONS")
    require(value.get("previous") == PREVIOUS, "PREVIOUS_RELEASE")
    require(isinstance(value.get("state_sha256"), str) and SHA.fullmatch(value["state_sha256"]), "DATABASE_STATE_HASH")
    free = value.get("free_bytes")
    require(type(free) is int and free >= request.minimum_free_bytes, "INSUFFICIENT_CAPACITY")
    expected = MIGRATIONS if migrated else {key: MIGRATIONS[key] for key in ("1", "2", "3", "4")}
    require(value.get("checksums") == expected, "DATABASE_SCHEMA_PREFIX")
    identities = value.get("identities", {})
    for role in ("owner", "writer"):
        identity = identities.get(role, {})
        require(identity.get("database") == request.database and identity.get("port") == 5432, "DATABASE_IDENTITY")
        require(identity.get("host") in {"127.0.0.1", "::1"}, "LOOPBACK_ONLY")
        require(identity.get("role") == f"{request.database}_{role}", "SEPARATE_DATABASE_ROLES")
        version = identity.get("version_num")
        require(type(version) is int and 150000 <= version < 160000, "POSTGRES15_REQUIRED")
    require(identities.get("owner", {}).get("host") == identities.get("writer", {}).get("host"), "SAME_SERVER")
    require(value.get("runtime_safe") is True, "RUNTIME_PRIVILEGES")
    require(not migrated or value.get("new_tables_crud") is True, "NEW_TABLE_PRIVILEGES")
    queues = value.get("queues", {})
    require(queues == {"queued": 0, "running": 0, "leases": 0}, "NONEMPTY_QUEUE")
    require(all(type(count) is int for count in queues.values()), "QUEUE_COUNT_TYPE")
    sessions = value.get("other_database_sessions")
    require(type(sessions) is int and sessions == 0, "UNFENCED_DATABASE_WRITER")
    require(set(value.get("writers", {})) == set(request.units), "MISSING_WRITER")
    require(
        all(item == {"inactive": True, "boot_disabled": True} for item in value["writers"].values()),
        "WRITER_ACTIVE",
    )
    require(value.get("maintenance") is True and value.get("fence_held") is True, "WRITER_FENCE")
    require(request.scope != "live" or value.get("hermes_fence_held") is True, "HERMES_WRITER_FENCE")
    require(value.get("model") == {"model": "k3", "base": MODEL_BASE, "new_port": False}, "MODEL_CONFIGURATION")


def validate_backup(request: Request, backup: dict[str, Any], snapshot: dict[str, Any]) -> None:
    require(backup.get("schema") == "b1-quiesced-backup-v1", "BACKUP_SCHEMA")
    require(
        backup.get("operation_id") == request.operation_id and backup.get("database") == request.database,
        "BACKUP_SCOPE",
    )
    require(backup.get("source_state_sha256") == snapshot.get("state_sha256"), "BACKUP_STATE_CHANGED")
    require(
        backup.get("target") == TARGET and backup.get("manifest_sha256") == request.manifest_sha256,
        "BACKUP_SOURCE",
    )
    require(backup.get("mode") == "0600" and backup.get("body_free_withdrawals") is True, "BACKUP_PRIVACY")
    for key in ("dump_sha256", "withdrawals_sha256"):
        require(isinstance(backup.get(key), str) and SHA.fullmatch(backup[key]), "BACKUP_HASH")


def validate_restore(request: Request, backup: dict[str, Any], proof: dict[str, Any]) -> None:
    require(proof.get("schema") == "b1-isolated-restore-proof-v1", "RESTORE_PROOF_SCHEMA")
    require(proof.get("backup_sha256") == digest(backup), "RESTORE_BACKUP_BINDING")
    require(proof.get("target") == TARGET and proof.get("manifest_sha256") == request.manifest_sha256, "RESTORE_SOURCE")
    require(proof.get("database") == request.restore_database, "SEPARATE_RESTORE_TARGET")
    require(proof.get("checksums") == MIGRATIONS, "RESTORE_FORWARD_SCHEMA")
    for name in (
        "actual_pg_restore",
        "latest_withdrawals_replayed",
        "sent_uncertain_protected",
        "runtime_safe",
    ):
        require(proof.get(name) is True, "RESTORE_NOT_VERIFIED")
    require(
        all(type(proof.get(key)) is int and proof[key] == 0 for key in ("model_calls", "external_sends")),
        "RESTORE_EXTERNAL_EFFECT",
    )

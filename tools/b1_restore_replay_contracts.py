"""Stage-only restore replay inputs; production rollback is a separate authorization."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from tools.core_incremental_contracts import EXPECTED_MANIFEST, MIGRATIONS, TARGET

DATABASE = "zhiming_core_b1_restore"
DSN_ENV = "B1_RESTORE_OWNER_DSN"
SHA = re.compile(r"[0-9a-f]{64}")


class ReplayRejected(RuntimeError):
    """The CLI exposes a fixed code, never private inputs or provider diagnostics."""


def require(condition: object, code: str) -> None:
    if not condition:
        raise ReplayRejected(code)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path: Path, *, private: bool = False, local_drill: bool = False) -> None:
    require(
        path.is_file() and not any(item.is_symlink() for item in (path, *path.parents)),
        "REGULAR_FILE_REQUIRED",
    )
    if private and (os.name == "posix" or not local_drill):
        require(path.stat().st_mode & 0o077 == 0, "PRIVATE_FILE_REQUIRED")


@dataclass(frozen=True)
class RestoreRequest:
    operation_id: str
    scope: str
    database: str
    schema: str
    candidate_source: Path
    candidate_python: Path
    ledger: Path
    ledger_sha256: str
    local_drill: bool = False

    def validate(self) -> None:
        require(self.scope == "stage" and self.database == DATABASE, "STAGE_RESTORE_ONLY")
        require(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", self.operation_id), "OPERATION_ID")
        require(
            self.schema == "mingjing_core"
            or self.local_drill
            and re.fullmatch(r"b1_replay_[0-9a-f]{12,32}", self.schema),
            "SCHEMA_SCOPE",
        )
        require(SHA.fullmatch(self.ledger_sha256), "LEDGER_HASH_FORMAT")
        require(
            self.candidate_source.is_absolute() and self.candidate_python.is_absolute(),
            "ABSOLUTE_CANDIDATE",
        )
        regular(self.ledger, private=True, local_drill=self.local_drill)
        require(file_hash(self.ledger) == self.ledger_sha256, "LEDGER_CHANGED")

    def dsn(self) -> str:
        value = os.environ.get(DSN_ENV, "")
        require(value, "RESTORE_DSN_MISSING")
        try:
            fields = conninfo_to_dict(value)
        except Exception:
            raise ReplayRejected("RESTORE_DSN_INVALID") from None
        require(fields.get("host") in {"127.0.0.1", "::1"}, "LOOPBACK_ONLY")
        require(
            not fields.get("hostaddr") or fields["hostaddr"] == fields["host"],
            "HOSTADDR_SCOPE",
        )
        ports = {"5432", "55480", "55481"} if self.local_drill else {"5432"}
        require(fields.get("port", "5432") in ports, "RESTORE_PORT")
        require(
            fields.get("dbname") == DATABASE and fields.get("user") == DATABASE + "_owner",
            "RESTORE_IDENTITY",
        )
        require(
            not any(key in fields for key in ("service", "options")),
            "RESTORE_DSN_OPTIONS",
        )
        return value


def verify_candidate(root: Path) -> None:
    require(root.is_dir() and not root.is_symlink(), "CANDIDATE_DIRECTORY")
    manifest_path = root / "__release_manifest__.json"
    regular(manifest_path)
    require(file_hash(manifest_path) == EXPECTED_MANIFEST, "PINNED_MANIFEST")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        manifest.get("schema") == "core3-release-v1" and manifest.get("commit") == TARGET,
        "PINNED_CANDIDATE",
    )
    require(isinstance(manifest.get("files"), dict) and manifest["files"], "CANDIDATE_FILES")
    for name, record in manifest["files"].items():
        relative = PurePosixPath(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts and "\\" not in name,
            "CANDIDATE_MEMBER",
        )
        path = root.joinpath(*relative.parts)
        regular(path)
        require(file_hash(path) == record.get("sha256"), "CANDIDATE_FILE_CHANGED")
    verify_members(
        root,
        {*manifest["files"], "__release_manifest__.json", "calculator-validation.json"},
    )
    actual = {
        str(int(path.name[:4])): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in (root / "mingjing_core/repositories/migrations").glob("[0-9][0-9][0-9][0-9]_*.sql")
    }
    require(actual == MIGRATIONS, "PINNED_MIGRATIONS")


def verify_members(root: Path, allowed: set[str]) -> None:
    def reject_traversal(error: OSError) -> None:
        raise ReplayRejected("CANDIDATE_TRAVERSAL_FAILED") from None

    for directory, names, filenames in os.walk(root, followlinks=False, onerror=reject_traversal):
        current = Path(directory)
        for name in names[:]:
            item = current / name
            require(not item.is_symlink(), "CANDIDATE_SYMLINK")
            if name == "__pycache__" or item == root / "venv":
                names.remove(name)
        for name in filenames:
            item = current / name
            require(not item.is_symlink(), "CANDIDATE_SYMLINK")
            require(
                item.relative_to(root).as_posix() in allowed,
                "UNEXPECTED_CANDIDATE_FILE",
            )


def load_document(request: RestoreRequest) -> dict[str, Any]:
    require(request.ledger.stat().st_size <= 16_000_000, "LEDGER_SIZE")
    document = json.loads(request.ledger.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "LEDGER_SCHEMA")
    require(
        set(document) == {"schema", "owners", "tarot_requests", "deleted_draws", "delivery_receipts"},
        "LEDGER_FIELDS",
    )
    require(document["schema"] == "core3-withdrawals-v2", "LEDGER_SCHEMA")
    require(
        all(
            isinstance(document[key], list)
            for key in (
                "owners",
                "tarot_requests",
                "deleted_draws",
                "delivery_receipts",
            )
        ),
        "LEDGER_ARRAYS",
    )
    owners = []
    for ledger in document["owners"]:
        require(
            isinstance(ledger, dict) and set(ledger) == {"schema_version", "owner_user_id", "revocations"},
            "PRIVACY_FIELDS",
        )
        require(
            ledger["schema_version"] == "core3.0" and isinstance(ledger["owner_user_id"], str),
            "PRIVACY_SCHEMA",
        )
        require(isinstance(ledger["revocations"], list), "PRIVACY_ROWS")
        owners.append(ledger["owner_user_id"])
        for row in ledger["revocations"]:
            require(
                isinstance(row, dict) and set(row) == {"kind", "entity_id", "operation", "metadata"},
                "REVOCATION_FIELDS",
            )
            require(isinstance(row["metadata"], dict), "REVOCATION_METADATA")
            allowed = {
                "message_id",
                "start",
                "end",
                "fact_ids",
                "source_ids",
                "source",
                "legacy_id",
            }
            require(set(row["metadata"]) <= allowed, "REVOCATION_BODY_FORBIDDEN")
    require(len(owners) == len(set(owners)) and all(owners), "EXPLICIT_UNIQUE_OWNERS")
    return document

"""Immutable reviewed inputs for the core-only restore foundation; no publication authority."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.core_incremental_contracts import MIGRATIONS as B1_MIGRATIONS

PROFILE = "core-only-1-8-v1"
MIGRATIONS = {**B1_MIGRATIONS, "8": "5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb"}
LOCKS = ("requirements-core.lock", "requirements-charts.lock", "k3-tokenizer.lock.json")
RELEASE_ROOT = Path("/root/zhiming-core-releases")
RESTORE_DATABASE = "zhiming_core_first_restore"
DSN_ENV = {"owner": "FIRST_RELEASE_OWNER_DSN", "writer": "FIRST_RELEASE_WRITER_DSN"}


class RestoreRejected(RuntimeError):
    """Only fixed body-free codes cross the command boundary."""


def require(value: object, code: str) -> None:
    if not value:
        raise RestoreRejected(code)


def digest(value: object, length: int = 64) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None


def ordinary(path: Path, *, directory: bool = False) -> None:
    require(path.is_absolute() and ".." not in path.parts, "ABSOLUTE_SAFE_PATH_REQUIRED")
    for item in (path, *path.parents):
        observed = item.lstat()
        linked = stat.S_ISLNK(observed.st_mode) or getattr(observed, "st_file_attributes", 0) & 0x400
        require(not linked, "LINKED_PATH_REJECTED")
    require(path.is_dir() if directory else path.is_file(), "ORDINARY_PATH_REQUIRED")


def read_json(path: Path) -> dict[str, Any]:
    try:
        ordinary(path)
        require(path.stat().st_size <= 16_000_000, "INPUT_SIZE_LIMIT")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise RestoreRejected("INPUT_UNREADABLE") from None
    require(isinstance(value, dict), "INPUT_OBJECT_REQUIRED")
    return value


@dataclass(frozen=True)
class ReleasePin:
    candidate: str
    manifest_sha256: str
    migrations: tuple[tuple[str, str], ...]
    locks: tuple[tuple[str, str], ...]
    profile: str = PROFILE

    def __post_init__(self) -> None:
        require(self.profile == PROFILE, "REVIEWED_CORE_ONLY_PROFILE_REQUIRED")
        require(digest(self.candidate, 40) and digest(self.manifest_sha256), "RELEASE_PIN_DIGEST")
        require(
            type(self.migrations) is tuple and all(type(row) is tuple and len(row) == 2 for row in self.migrations),
            "IMMUTABLE_MIGRATION_PIN_REQUIRED",
        )
        require(dict(self.migrations) == MIGRATIONS and len(self.migrations) == 8, "EXACT_MIGRATIONS_1_8_REQUIRED")
        require(
            type(self.locks) is tuple and all(type(row) is tuple and len(row) == 2 for row in self.locks),
            "IMMUTABLE_LOCK_PIN_REQUIRED",
        )
        require(len(self.locks) == 3 and set(dict(self.locks)) == set(LOCKS), "EXACT_THREE_LOCKS_REQUIRED")
        require(all(digest(value) for _, value in self.locks), "LOCK_PIN_DIGEST")

    @classmethod
    def parse(cls, value: dict[str, Any]) -> ReleasePin:
        require(
            set(value) == {"schema", "profile", "candidate", "manifest_sha256", "migrations", "locks"},
            "RELEASE_PIN_FIELDS",
        )
        require(value["schema"] == "first-release-pin-v1", "RELEASE_PIN_SCHEMA")
        require(isinstance(value["migrations"], dict) and isinstance(value["locks"], dict), "RELEASE_PIN_MAPS")
        return cls(
            value["candidate"],
            value["manifest_sha256"],
            tuple(sorted(value["migrations"].items())),
            tuple(sorted(value["locks"].items())),
            value["profile"],
        )


@dataclass(frozen=True)
class RestoreContract:
    operation_id: str
    database: str
    candidate_source: Path
    local_drill: bool = False

    @classmethod
    def parse(cls, value: dict[str, Any]) -> RestoreContract:
        require(
            set(value) == {"schema", "operation_id", "database", "candidate_source", "local_drill"},
            "RESTORE_CONTRACT_FIELDS",
        )
        require(value["schema"] == "first-release-restore-contract-v1", "RESTORE_CONTRACT_SCHEMA")
        require(isinstance(value["candidate_source"], str), "CANDIDATE_PATH_REQUIRED")
        return cls(value["operation_id"], value["database"], Path(value["candidate_source"]), value["local_drill"])

    def validate_scope(self, pin: ReleasePin, *, workspace: Path | None = None) -> None:
        self.validate_database()
        root = RELEASE_ROOT
        if self.local_drill:
            require(isinstance(workspace, Path), "EXPLICIT_LOCAL_WORKSPACE_REQUIRED")
            ordinary(workspace, directory=True)
            root = workspace / "private" / ("first-release-" + self.operation_id[3:])
        require(self.candidate_source == root / pin.candidate, "FIXED_CANDIDATE_SOURCE_REQUIRED")
        ordinary(self.candidate_source, directory=True)

    def validate_database(self) -> None:
        require(
            isinstance(self.operation_id, str) and re.fullmatch(r"fr-[0-9a-f]{32}", self.operation_id),
            "RESTORE_OPERATION_ID",
        )
        require(type(self.local_drill) is bool, "LOCAL_MODE_TYPE")
        expected_database = "fr_restore_" + self.operation_id[3:] if self.local_drill else RESTORE_DATABASE
        require(self.database == expected_database, "NEW_DATABASE_ONLY")

    def dsns(self, environment: Mapping[str, str] | None = None) -> dict[str, str]:
        self.validate_database()
        source = os.environ if environment is None else environment
        require(not any(key.startswith("PG") and value for key, value in os.environ.items()), "IMPLICIT_PG_REJECTED")
        require(not any(key.startswith("PG") and value for key, value in source.items()), "IMPLICIT_PG_REJECTED")
        result, identities = {}, []
        for role, variable in DSN_ENV.items():
            require(source.get(variable), "EXPLICIT_DSN_REQUIRED")
            try:
                fields = conninfo_to_dict(source[variable])
            except Exception:
                raise RestoreRejected("INVALID_EXPLICIT_DSN") from None
            allowed = {"host", "hostaddr", "port", "dbname", "user", "password", "connect_timeout", "passfile"}
            require(not set(fields) - allowed, "DSN_OPTIONS_REJECTED")
            require(fields.get("host") in {"127.0.0.1", "::1"}, "LOOPBACK_LITERAL_REQUIRED")
            require(fields.get("hostaddr", fields["host"]) == fields["host"], "DSN_HOSTADDR_MISMATCH")
            require(fields.get("port") in ({"55480", "55481"} if self.local_drill else {"5432"}), "EXPLICIT_PORT")
            require(
                fields.get("dbname") == self.database and fields.get("user") == self.database + "_" + role,
                "DSN_IDENTITY_MISMATCH",
            )
            require(fields.get("passfile", os.devnull) == os.devnull, "DSN_PASSFILE_REJECTED")
            identities.append((fields["host"], fields["port"], fields["dbname"]))
            result[role] = make_conninfo(
                **dict(fields, hostaddr=fields["host"], passfile=os.devnull, connect_timeout="5")
            )
        require(identities[0] == identities[1], "OWNER_WRITER_LOCATION_MISMATCH")
        return result

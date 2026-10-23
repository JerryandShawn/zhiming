"""Reviewed, local-only original-prefix restore inputs; not a production restore proof."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, digest, ordinary, require
from tools.first_release_restore import validate_inputs


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


@dataclass(frozen=True)
class DumpPin:
    candidate: str
    manifest_sha256: str
    dump_sha256: str
    pg_restore_sha256: str
    source_migrations: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> DumpPin:
        require(
            set(value)
            == {"schema", "candidate", "manifest_sha256", "dump_sha256", "pg_restore_sha256", "source_migrations"},
            "LOCAL_DUMP_PIN_FIELDS",
        )
        require(value["schema"] == "first-release-local-dump-pin-v1", "LOCAL_DUMP_PIN_SCHEMA")
        require(isinstance(value["source_migrations"], dict), "LOCAL_SOURCE_PREFIX_REQUIRED")
        return cls(
            value["candidate"],
            value["manifest_sha256"],
            value["dump_sha256"],
            value["pg_restore_sha256"],
            tuple(sorted(value["source_migrations"].items())),
        )

    def validate(self, release: ReleasePin) -> None:
        require(
            self.candidate == release.candidate and self.manifest_sha256 == release.manifest_sha256,
            "DUMP_CANDIDATE_BINDING",
        )
        require(digest(self.dump_sha256) and digest(self.pg_restore_sha256), "LOCAL_DUMP_PROGRAM_HASH_REQUIRED")
        require(
            type(self.source_migrations) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.source_migrations),
            "IMMUTABLE_SOURCE_PREFIX",
        )
        require(1 <= len(self.source_migrations) <= 7, "LOCAL_PREFIX_1_7_ONLY")
        expected = {
            str(version): dict(release.migrations)[str(version)]
            for version in range(1, len(self.source_migrations) + 1)
        }
        require(dict(self.source_migrations) == expected, "LOCAL_SOURCE_PREFIX_MISMATCH")


@dataclass(frozen=True)
class LocalInputs:
    release: ReleasePin
    contract: RestoreContract
    dump_pin: DumpPin
    dump: Path
    pg_restore: Path
    workspace: Path

    def validate(self) -> dict[str, Any]:
        require(self.contract.local_drill is True, "LOCAL_DRILL_ONLY_NO_STAGE_OR_PRODUCTION")
        result = validate_inputs(self.release, self.contract, workspace=self.workspace)
        self.dump_pin.validate(self.release)
        require(self.dump == self.contract.candidate_source.parent / "backup.dump", "FIXED_LOCAL_DUMP_PATH")
        ordinary(self.dump)
        require(5 < self.dump.stat().st_size <= 1024**3, "LOCAL_DUMP_SIZE")
        with self.dump.open("rb") as stream:
            require(stream.read(5) == b"PGDMP", "CUSTOM_DUMP_REQUIRED")
        require(file_hash(self.dump) == self.dump_pin.dump_sha256, "REVIEWED_DUMP_CHANGED")
        ordinary(self.pg_restore)
        require(
            self.pg_restore.name in {"pg_restore", "pg_restore.exe"} and os.access(self.pg_restore, os.X_OK),
            "PG_RESTORE_EXECUTABLE_REQUIRED",
        )
        require(file_hash(self.pg_restore) == self.dump_pin.pg_restore_sha256, "REVIEWED_PG_RESTORE_CHANGED")
        return {
            **result,
            "dump_sha256": self.dump_pin.dump_sha256,
            "pg_restore_sha256": self.dump_pin.pg_restore_sha256,
            "source_migrations": dict(self.dump_pin.source_migrations),
            "local_pg_restore_completed": False,
        }

    def connections(self, environment: Mapping[str, str] | None = None) -> dict[str, str]:
        require(self.contract.local_drill is True, "LOCAL_DRILL_ONLY_NO_STAGE_OR_PRODUCTION")
        source = os.environ if environment is None else environment
        result = self.contract.dsns(source)
        try:
            fields = conninfo_to_dict(source.get("FIRST_RELEASE_ADMIN_DSN", ""))
        except Exception:
            raise RestoreRejected("LOCAL_ADMIN_DSN_REQUIRED") from None
        allowed = {"host", "hostaddr", "port", "dbname", "user", "password", "passfile", "connect_timeout"}
        require(fields and not set(fields) - allowed, "LOCAL_ADMIN_DSN_OPTIONS")
        owner = conninfo_to_dict(result["owner"])
        require(fields.get("host") == owner["host"] and fields.get("port") == owner["port"], "LOCAL_ADMIN_LOCATION")
        require(fields.get("hostaddr", fields["host"]) == fields["host"], "LOCAL_ADMIN_HOSTADDR")
        require(fields.get("dbname") in {"postgres", "core_test_main"} and fields.get("user"), "LOCAL_ADMIN_CONTROL_DB")
        require(fields.get("passfile", os.devnull) == os.devnull, "LOCAL_ADMIN_PASSFILE")
        result["admin"] = make_conninfo(
            **dict(fields, hostaddr=fields["host"], passfile=os.devnull, connect_timeout="5")
        )
        return result

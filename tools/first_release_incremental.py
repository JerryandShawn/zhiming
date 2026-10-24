"""Explicit backup of an existing synthetic local Core database; never an upgrade authorization."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict, make_conninfo

from tools.first_release_contracts import (
    ReleasePin,
    RestoreRejected,
    digest,
    ordinary,
    read_json,
    require,
)
from tools.first_release_restore import SafeParser
from tools.first_release_source import verify_source

HERE = Path(__file__).parent
CONTROL_NAMES = frozenset(
    {
        "first_release_incremental.py",
        "first_release_admission.py",
        "first_release_incremental_pg.py",
        "first_release_session_observer.py",
        "first_release_incremental_worker.py",
        "first_release_writer_fence.py",
        "first_release_replay_worker.py",
        "first_release_source.py",
        "first_release_contracts.py",
        "core_incremental_contracts.py",
    }
)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class SourcePin:
    database: str
    system_identifier: str
    database_oid: int
    owner_oid: int
    writer_oid: int
    owners: tuple[str, ...]
    migrations: tuple[tuple[str, str], ...]

    @classmethod
    def parse(cls, value: dict[str, Any]) -> SourcePin:
        fields = {
            "database",
            "system_identifier",
            "database_oid",
            "owner_oid",
            "writer_oid",
            "owners",
            "migrations",
        }
        require(
            isinstance(value, dict) and set(value) == fields,
            "INCREMENTAL_SOURCE_PIN_FIELDS",
        )
        require(
            isinstance(value["owners"], list) and isinstance(value["migrations"], dict),
            "INCREMENTAL_SOURCE_PIN_TYPES",
        )
        return cls(
            **{key: value[key] for key in fields - {"owners", "migrations"}},
            owners=tuple(value["owners"]),
            migrations=tuple(sorted(value["migrations"].items())),
        )

    def validate(self, operation: str, release: ReleasePin) -> None:
        require(
            self.database == "fr_upgrade_" + operation[3:],
            "INCREMENTAL_SYNTHETIC_EXISTING_DATABASE_ONLY",
        )
        require(
            isinstance(self.system_identifier, str) and re.fullmatch(r"[0-9]{15,20}", self.system_identifier),
            "INCREMENTAL_SYSTEM_IDENTIFIER",
        )
        require(
            all(
                type(value) is int and 0 < value < 2**32
                for value in (self.database_oid, self.owner_oid, self.writer_oid)
            )
            and self.owner_oid != self.writer_oid,
            "INCREMENTAL_EXACT_OIDS_REQUIRED",
        )
        require(
            type(self.owners) is tuple
            and self.owners
            and all(isinstance(owner, str) and 0 < len(owner) <= 200 for owner in self.owners)
            and tuple(sorted(set(self.owners))) == self.owners,
            "INCREMENTAL_OWNER_SET",
        )
        require(
            type(self.migrations) is tuple and all(type(row) is tuple and len(row) == 2 for row in self.migrations),
            "INCREMENTAL_IMMUTABLE_PREFIX",
        )
        require(
            len(self.migrations) in {4, 7}
            and dict(self.migrations)
            == {str(version): dict(release.migrations)[str(version)] for version in range(1, len(self.migrations) + 1)},
            "INCREMENTAL_EXACT_PREFIX_4_7_REQUIRED",
        )


@dataclass(frozen=True)
class BackupInputs:
    operation_id: str
    release: ReleasePin
    source: SourcePin
    python: Path
    pg_dump: Path
    python_sha256: str
    pg_dump_sha256: str
    controls: tuple[tuple[str, str], ...]
    workspace: Path
    local_drill: bool = True

    @classmethod
    def parse(cls, value: dict[str, Any], workspace: Path) -> BackupInputs:
        require(
            set(value)
            == {
                "schema",
                "operation_id",
                "local_drill",
                "release",
                "source",
                "runtime",
                "controls",
            },
            "INCREMENTAL_PIN_FIELDS",
        )
        require(
            value["schema"] == "first-release-local-incremental-backup-pin-v1",
            "INCREMENTAL_PIN_SCHEMA",
        )
        runtime = value["runtime"]
        require(
            isinstance(runtime, dict)
            and set(runtime) == {"python", "pg_dump", "python_sha256", "pg_dump_sha256"}
            and isinstance(value["controls"], dict),
            "INCREMENTAL_RUNTIME_PIN_FIELDS",
        )
        return cls(
            value["operation_id"],
            ReleasePin.parse(value["release"]),
            SourcePin.parse(value["source"]),
            Path(runtime["python"]),
            Path(runtime["pg_dump"]),
            runtime["python_sha256"],
            runtime["pg_dump_sha256"],
            tuple(sorted(value["controls"].items())),
            workspace,
            value["local_drill"],
        )

    @property
    def operation_dir(self) -> Path:
        return self.workspace / "private" / ("first-incremental-" + self.operation_id[3:])

    @property
    def candidate_source(self) -> Path:
        return self.operation_dir / self.release.candidate

    @property
    def fence_key(self) -> str:
        return "first-release-writer:" + self.source.system_identifier + ":" + str(self.source.database_oid)

    @property
    def fence_path(self) -> Path:
        return (
            self.workspace
            / "private"
            / "first-release-writers"
            / (self.source.system_identifier + "-" + str(self.source.database_oid) + ".lock")
        )

    @property
    def maintenance(self) -> Path:
        return self.fence_path.with_suffix(".maintenance.json")

    def validate(self) -> dict[str, Any]:
        require(self.local_drill is True, "INCREMENTAL_LOCAL_ONLY_NO_FORMAL")
        require(type(self.release) is ReleasePin and type(self.source) is SourcePin, "INCREMENTAL_TYPED_PINS_REQUIRED")
        require(
            isinstance(self.operation_id, str) and re.fullmatch(r"fr-[0-9a-f]{32}", self.operation_id),
            "INCREMENTAL_OPERATION_REQUIRED",
        )
        ordinary(self.workspace, directory=True)
        self.source.validate(self.operation_id, self.release)
        require(
            type(self.controls) is tuple
            and all(type(row) is tuple and len(row) == 2 for row in self.controls)
            and len(self.controls) == len(CONTROL_NAMES)
            and set(dict(self.controls)) == CONTROL_NAMES,
            "INCREMENTAL_CONTROL_PIN_FIELDS",
        )
        for name, expected in self.controls:
            ordinary(HERE / name)
            require(
                digest(expected) and file_hash(HERE / name) == expected,
                "INCREMENTAL_REVIEWED_CONTROL_CHANGED",
            )
        for program, expected in (
            (self.python, self.python_sha256),
            (self.pg_dump, self.pg_dump_sha256),
        ):
            ordinary(program)
            require(
                digest(expected) and os.access(program, os.X_OK) and file_hash(program) == expected,
                "INCREMENTAL_REVIEWED_PROGRAM_CHANGED",
            )
        require(
            self.pg_dump.name in {"pg_dump", "pg_dump.exe"},
            "INCREMENTAL_PG_DUMP_REQUIRED",
        )
        source = verify_source(self.candidate_source, self.release)
        return {
            **source,
            "schema": "first-release-local-incremental-backup-validation-v1",
            "database_connections": 0,
            "processes": 0,
            "file_writes": 0,
            "backup_captured": False,
            "source_upgraded": False,
            "native_restore_completed": False,
            "linux_attestation": False,
            "publication": False,
        }


def connections(inputs: BackupInputs, environment: dict[str, str] | None) -> dict[str, str]:
    source = os.environ if environment is None else environment
    require(
        not any(key.startswith("PG") and value for values in (os.environ, source) for key, value in values.items()),
        "INCREMENTAL_IMPLICIT_PG_REJECTED",
    )
    result, locations = {}, []
    allowed = {
        "host",
        "hostaddr",
        "port",
        "dbname",
        "user",
        "password",
        "passfile",
        "connect_timeout",
    }
    for role in ("owner", "writer", "admin"):
        try:
            fields = conninfo_to_dict(source.get("FIRST_INCREMENTAL_" + role.upper() + "_DSN", ""))
        except Exception:
            raise RestoreRejected("INCREMENTAL_EXPLICIT_DSN_REQUIRED") from None
        require(
            fields
            and set(fields) <= allowed
            and fields.get("host") in {"127.0.0.1", "::1"}
            and fields.get("port") in {"55480", "55481"},
            "INCREMENTAL_DSN_LOCATION",
        )
        require(
            fields.get("hostaddr", fields["host"]) == fields["host"]
            and fields.get("passfile", os.devnull) == os.devnull
            and fields.get("user"),
            "INCREMENTAL_DSN_OPTIONS",
        )
        if role == "admin":
            require(
                fields.get("dbname") in {"postgres", "core_test_main"},
                "INCREMENTAL_ADMIN_CONTROL_DATABASE",
            )
        else:
            require(
                fields.get("dbname") == inputs.source.database
                and fields.get("user") == inputs.source.database + "_" + role,
                "INCREMENTAL_DSN_ROLE",
            )
        locations.append((fields["host"], fields["port"]))
        result[role] = make_conninfo(
            **dict(
                fields,
                hostaddr=fields["host"],
                passfile=os.devnull,
                connect_timeout="5",
            )
        )
    require(len(set(locations)) == 1, "INCREMENTAL_ONE_SERVER_REQUIRED")
    return result


def execute(
    inputs: BackupInputs,
    *,
    backup_local: bool = False,
    close_admission_local: bool = False,
    use_admission: bool = False,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    receipt = inputs.validate()
    require(
        all(type(value) is bool for value in (backup_local, close_admission_local, use_admission)),
        "INCREMENTAL_EXPLICIT_BACKUP_FLAG",
    )
    require(not (backup_local and close_admission_local), "INCREMENTAL_ACTION_FLAGS_REJECTED")
    require(not use_admission or backup_local, "INCREMENTAL_ADMISSION_REQUIRES_BACKUP")
    if not (backup_local or close_admission_local):
        return receipt
    dsns = connections(inputs, environment)
    if close_admission_local:
        from tools.first_release_admission import close_admission

        return close_admission(inputs, dsns)
    from tools.first_release_incremental_pg import backup

    return backup(inputs, dsns, use_admission=use_admission)


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__)
    parser.add_argument("--pin", required=True, type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--backup-local", action="store_true")
    action.add_argument("--close-admission-local", action="store_true")
    parser.add_argument("--use-admission", action="store_true")
    try:
        args = parser.parse_args(argv)
        receipt = execute(
            BackupInputs.parse(read_json(args.pin), Path.cwd()),
            backup_local=args.backup_local,
            close_admission_local=args.close_admission_local,
            use_admission=args.use_admission,
        )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_cleanup": False}))
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "INCREMENTAL_BACKUP_FAILED_OUTPUTS_RETAINED",
                    "automatic_cleanup": False,
                }
            )
        )
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

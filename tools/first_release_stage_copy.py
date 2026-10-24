"""F-scoped read-only stage backup into a new closed copy; never adopt or delete."""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_database_metadata import apply_metadata, capture, semantic, validate
from tools.first_release_local_restore import process_environment
from tools.first_release_native_exchange import (
    Scope,
    _absent,
    _environment,
    _restore_program,
    control,
    file_hash,
    write_private,
)
from tools.first_release_restore import SafeParser


@dataclass(frozen=True)
class CopyScope(Scope):
    @property
    def source(self) -> str:
        return self.original if self.local_drill else "zhiming_core_stage"

    @property
    def target(self) -> str:
        return self.replacement if self.local_drill else "zhiming_core_fr_stage"


def _dump(program: Path, dsn: str, database: str, output: Path) -> None:
    fields = conninfo_to_dict(dsn)
    environment = process_environment(dsn)
    version = subprocess.run([str(program), "--version"], env=environment, capture_output=True, timeout=10)
    require(version.returncode == 0 and re.search(rb"PostgreSQL\) 15\.[0-9]+", version.stdout), "STAGE_DUMP15_REQUIRED")
    environment["PGOPTIONS"] = "-c default_transaction_read_only=on"
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        result = subprocess.run(
            [
                str(program),
                "--host=" + fields["host"],
                "--port=" + fields["port"],
                "--username=" + fields["user"],
                "--dbname=" + database,
                "--no-password",
                "--format=custom",
                "--lock-wait-timeout=5000",
            ],
            env=environment,
            stdout=stream,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=1800,
        )
        stream.flush()
        os.fsync(stream.fileno())
    require(result.returncode == 0, "STAGE_READONLY_DUMP_FAILED_PRESERVED")


def copy_stage(
    scope: CopyScope,
    workspace: Path,
    pg_dump: Path,
    pg_restore: Path,
    dump_program_sha: str,
    restore_program_sha: str,
    *,
    environment=None,
) -> dict:
    scope.validate()
    ordinary(workspace, directory=True)
    require(scope.local_drill or workspace.stat().st_mode & 0o077 == 0, "STAGE_PRIVATE_WORKSPACE")
    require(
        file_hash(pg_dump) == dump_program_sha and file_hash(pg_restore) == restore_program_sha,
        "STAGE_PROGRAM_PIN_CHANGED",
    )
    backup, metadata = workspace / "original-stage.dump", workspace / "source-database-metadata.json"
    require(not any(os.path.lexists(path) for path in (backup, metadata)), "STAGE_NEW_BACKUP_REQUIRED")
    with control(scope, environment) as (connection, dsn):
        _absent(connection, scope.target)
        snapshot = capture(connection, scope.source)
        validate(connection, snapshot)
        write_private(metadata, snapshot)
        _dump(pg_dump, dsn, scope.source, backup)
        require(
            file_hash(pg_dump) == dump_program_sha and file_hash(pg_restore) == restore_program_sha,
            "STAGE_PROGRAM_PIN_CHANGED",
        )
        backup_sha = file_hash(backup)
        require(capture(connection, scope.source) == snapshot, "STAGE_SOURCE_METADATA_CHANGED")
        _create(connection, scope.target, snapshot)
        _restore_program(pg_restore, backup, dsn, scope.target)
        require(file_hash(backup) == backup_sha, "STAGE_BACKUP_CHANGED")
        with connection.transaction():
            apply_metadata(connection, scope.target, snapshot)
            connection.execute(
                sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.target))
            )
        restored = capture(connection, scope.target)
        require(semantic(restored) == semantic(snapshot), "STAGE_COPY_METADATA_MISMATCH")
        require(capture(connection, scope.source) == snapshot, "STAGE_SOURCE_METADATA_CHANGED")
    return {
        "schema": "first-release-stage-copy-v1",
        "status": "copied_closed",
        "operation": scope.operation,
        "source": scope.source,
        "source_oid": snapshot["oid"],
        "target": scope.target,
        "target_oid": restored["oid"],
        "backup_sha256": backup_sha,
        "metadata_sha256": file_hash(metadata),
        "pg_dump_sha256": dump_program_sha,
        "pg_restore_sha256": restore_program_sha,
        "source_readonly": True,
        "admission_opened": False,
        "automatic_retry": False,
    }


def _create(connection, target: str, snapshot: dict) -> None:
    connection.execute(
        sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}").format(
            sql.Identifier(target),
            sql.Identifier(snapshot["owner"]),
            sql.Literal(snapshot["encoding"]),
            sql.Literal(snapshot["collate"]),
            sql.Literal(snapshot["ctype"]),
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--pg-dump", type=Path, required=True)
    parser.add_argument("--pg-dump-sha256", required=True)
    parser.add_argument("--pg-restore", type=Path, required=True)
    parser.add_argument("--pg-restore-sha256", required=True)
    parser.add_argument("--admin-env-file", type=Path)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        args = parser.parse_args(argv)
        scope = CopyScope(args.operation, args.local_drill)
        scope.validate()
        if not args.apply:
            print(json.dumps({"status": "arguments_validated", "database_connections": 0, "model_calls": 0}))
            return 0
        output = args.workspace / "copy-receipt.json"
        require(not os.path.lexists(output), "STAGE_NEW_RECEIPT_REQUIRED")
        result = copy_stage(
            scope,
            args.workspace,
            args.pg_dump,
            args.pg_restore,
            args.pg_dump_sha256,
            args.pg_restore_sha256,
            environment=_environment(scope, args.admin_env_file),
        )
        write_private(output, result)
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "STAGE_COPY_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

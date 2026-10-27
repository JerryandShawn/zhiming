"""B7 empty-delta archive of the closed first-release copy; no live or original-stage target."""

from __future__ import annotations

import json
import os
from pathlib import Path

from psycopg import sql
from psycopg.conninfo import make_conninfo

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.first_release_contracts import RestoreRejected, ordinary, read_json, require
from tools.first_release_database_metadata import capture, validate
from tools.first_release_native_exchange import (
    Scope,
    _environment,
    control,
    file_hash,
    write_private,
)
from tools.first_release_restore import SafeParser
from tools.first_release_stage_copy import _dump
from tools.first_release_writer_fence import file_lock


def _closed_empty(connection, scope: Scope, snapshot: dict) -> None:
    validate(connection, snapshot)
    require(
        snapshot["database"] == scope.original and capture(connection, scope.original) == snapshot,
        "STAGE_BACKUP_METADATA_CHANGED",
    )
    observed = connection.execute(
        "SELECT NOT datallowconn AS closed,"
        "(SELECT count(*) FROM pg_stat_activity WHERE datid=d.oid) AS clients "
        "FROM pg_database d WHERE datname=%s",
        (scope.original,),
    ).fetchone()
    require(observed and observed["closed"] and observed["clients"] == 0, "STAGE_BACKUP_CLOSED_ZERO_REQUIRED")


def backup_closed(
    scope: Scope, workspace: Path, snapshot: dict, pg_dump: Path, program_hash: str, *, environment=None
) -> dict:
    scope.validate()
    ordinary(workspace, directory=True)
    require(scope.local_drill or workspace.stat().st_mode & 0o077 == 0, "STAGE_PRIVATE_WORKSPACE")
    backup, metadata = workspace / "empty-delta.dump", workspace / "empty-delta-metadata.json"
    with file_lock(workspace / "writer.lock", exclusive=True), control(scope, environment) as (admin, dsn):
        require(
            not any(
                os.path.lexists(workspace / name)
                for name in (
                    "empty-delta-started.json",
                    "empty-delta.dump",
                    "empty-delta-metadata.json",
                    "empty-delta-receipt.json",
                )
            ),
            "STAGE_BACKUP_ALREADY_STARTED_NO_RETRY",
        )
        require(file_hash(pg_dump) == program_hash, "STAGE_DUMP_BINARY_CHANGED")
        _closed_empty(admin, scope, snapshot)
        write_private(workspace / "empty-delta-started.json", {"operation": scope.operation, "oid": snapshot["oid"]})
        write_private(metadata, snapshot)
        # Only this new copy is briefly connectable for the read-only pg_dump connection.
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.original)))
        _prefix_eight(dsn, scope)
        _dump(pg_dump, dsn, scope.original, backup)
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.original)))
        _closed_empty(admin, scope, snapshot)
        require(file_hash(pg_dump) == program_hash, "STAGE_DUMP_BINARY_CHANGED")
    result = {
        "schema": "first-release-empty-delta-backup-v1",
        "status": "backed_up_closed",
        "operation": scope.operation,
        "database": scope.original,
        "database_oid": snapshot["oid"],
        "backup_sha256": file_hash(backup),
        "metadata_sha256": file_hash(metadata),
        "pg_dump_sha256": program_hash,
        "read_only_dump": True,
        "admission_opened": False,
        "automatic_retry": False,
    }
    write_private(workspace / "empty-delta-receipt.json", result)
    return result


def _prefix_eight(dsn: str, scope: Scope) -> None:
    repo = PostgresRepository(
        make_conninfo(
            dsn, dbname=scope.original, options="-c default_transaction_read_only=on -c search_path=public,pg_catalog"
        ),
        initialize=False,
        max_size=1,
    )
    try:
        require(repo.verify_schema()["version"] == 8, "STAGE_BACKUP_PREFIX8_REQUIRED")
        LangGraphRuntime(repo, initialize=False)
    except (EvidenceError, RuntimeError):
        raise RestoreRejected("STAGE_BACKUP_PREFIX8_CHECKPOINT_REQUIRED") from None
    finally:
        repo.close()


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--metadata-sha256", required=True)
    parser.add_argument("--pg-dump", type=Path, required=True)
    parser.add_argument("--pg-dump-sha256", required=True)
    parser.add_argument("--admin-env-file", type=Path)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        args = parser.parse_args(argv)
        scope = Scope(args.operation, args.local_drill)
        scope.validate()
        if not args.apply:
            print(json.dumps({"status": "arguments_validated", "database_connections": 0, "model_calls": 0}))
            return 0
        require(file_hash(args.metadata) == args.metadata_sha256, "STAGE_BACKUP_METADATA_CHANGED")
        result = backup_closed(
            scope,
            args.workspace,
            read_json(args.metadata),
            args.pg_dump,
            args.pg_dump_sha256,
            environment=_environment(scope, args.admin_env_file),
        )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "STAGE_BACKUP_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

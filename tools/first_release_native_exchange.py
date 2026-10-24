"""Explicit new-database restore/exchange for the first-stage copy; never live or original stage."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.first_release_contracts import RestoreRejected, digest, ordinary, read_json, require
from tools.first_release_database_metadata import apply_metadata, capture, semantic, validate
from tools.first_release_local_restore import process_environment
from tools.first_release_restore import SafeParser


@dataclass(frozen=True)
class Scope:
    operation: str
    local_drill: bool = False

    @property
    def original(self) -> str:
        return "frx_" + self.operation + "_live" if self.local_drill else "zhiming_core_fr_stage"

    @property
    def replacement(self) -> str:
        return ("frx_" if self.local_drill else "zhiming_core_fr_") + self.operation + "_restore"

    @property
    def failed(self) -> str:
        return ("frx_" if self.local_drill else "zhiming_core_fr_") + self.operation + "_failed"

    def validate(self) -> None:
        require(isinstance(self.operation, str) and re.fullmatch(r"[0-9a-f]{16}", self.operation), "EXCHANGE_OPERATION")
        require(type(self.local_drill) is bool, "EXCHANGE_LOCAL_MODE_TYPE")


def file_hash(path: Path) -> str:
    ordinary(path)
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def write_private(path: Path, value: dict[str, Any]) -> None:
    ordinary(path.parent, directory=True)
    observed = path.parent.stat()
    require(
        os.name == "nt" or not observed.st_mode & 0o077 and observed.st_uid == os.geteuid(),
        "EXCHANGE_PRIVATE_DIRECTORY_REQUIRED",
    )
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((json.dumps(value, sort_keys=True) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def control(scope: Scope, environment: dict[str, str] | None = None):
    scope.validate()
    require(scope.local_drill or os.name == "posix", "EXCHANGE_FORMAL_POSIX_REQUIRED")
    source = os.environ if environment is None else environment
    require(
        not any(key.startswith("PG") and value for key, value in {**os.environ, **source}.items()),
        "IMPLICIT_PG_REJECTED",
    )
    fields = conninfo_to_dict(source.get("FIRST_RELEASE_EXCHANGE_ADMIN_DSN", ""))
    require(not set(fields) - {"host", "port", "dbname", "user", "password", "connect_timeout"}, "EXCHANGE_DSN_OPTIONS")
    require(fields.get("host") in {"127.0.0.1", "::1"}, "EXCHANGE_LOOPBACK_REQUIRED")
    require(fields.get("port") in ({"55480", "55481"} if scope.local_drill else {"5432"}), "EXCHANGE_PORT")
    require(
        fields.get("dbname") in {"postgres", "core_test_main"}
        if scope.local_drill
        else fields.get("dbname") == "postgres",
        "EXCHANGE_CONTROL_DATABASE",
    )
    dsn = make_conninfo(**dict(fields, connect_timeout="5"), hostaddr=fields["host"], passfile=os.devnull)
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as connection:
        connection.execute("SET search_path=pg_catalog")
        row = connection.execute(
            "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
            "host(inet_server_addr()) AS host,inet_server_port() AS port,"
            "current_setting('server_version_num')::int AS version,"
            "(SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname=session_user) AS superuser"
        ).fetchone()
        require(
            row["database"] == fields["dbname"]
            and row["role"] == fields["user"] == row["session_role"]
            and row["host"] == fields["host"]
            and row["port"] == int(fields["port"])
            and 150000 <= row["version"] < 160000
            and row["superuser"] is True,
            "EXCHANGE_ACTUAL_ADMIN_IDENTITY",
        )
        require(
            connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS held", ("fr-exchange:" + scope.original,)
            ).fetchone()["held"],
            "EXCHANGE_IN_PROGRESS",
        )
        yield connection, dsn


def capture_to(scope: Scope, output: Path, *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    with control(scope, environment) as (connection, _):
        snapshot = capture(connection, scope.original)
        validate(connection, snapshot)
    write_private(output, snapshot)
    return {"status": "metadata_captured", "metadata_sha256": file_hash(output), "operation": scope.operation}


def _original(connection: Any, scope: Scope, snapshot: dict[str, Any]) -> None:
    require(snapshot["database"] == scope.original, "EXCHANGE_METADATA_DATABASE")
    validate(connection, snapshot)
    require(capture(connection, scope.original) == snapshot, "EXCHANGE_ORIGINAL_IDENTITY_OR_METADATA_CHANGED")


def _absent(connection: Any, database: str) -> None:
    row = connection.execute("SELECT oid FROM pg_catalog.pg_database WHERE datname=%s", (database,)).fetchone()
    require(row is None, "EXCHANGE_NEW_NAME_ALREADY_EXISTS")


def _restore_program(program: Path, backup: Path, dsn: str, database: str) -> None:
    fields = conninfo_to_dict(dsn)
    command = [
        str(program),
        "--host=" + fields["host"],
        "--port=" + fields["port"],
        "--username=" + fields["user"],
        "--dbname=" + database,
        "--no-password",
        "--exit-on-error",
        "--single-transaction",
        str(backup),
    ]
    environment = process_environment(dsn)
    version = subprocess.run([str(program), "--version"], env=environment, capture_output=True, timeout=10)
    require(
        version.returncode == 0 and re.search(rb"PostgreSQL\) 15\.[0-9]+", version.stdout),
        "EXCHANGE_RESTORE15_REQUIRED",
    )
    result = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL, capture_output=True, timeout=1800)
    require(result.returncode == 0, "EXCHANGE_PG_RESTORE_FAILED_TARGET_RETAINED")


def restore_new(
    scope: Scope,
    snapshot: dict[str, Any],
    backup: Path,
    backup_hash: str,
    program: Path,
    program_hash: str,
    *,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    require(digest(backup_hash) and file_hash(backup) == backup_hash, "EXCHANGE_BACKUP_CHANGED")
    require(digest(program_hash) and file_hash(program) == program_hash, "EXCHANGE_RESTORE_BINARY_CHANGED")
    with control(scope, environment) as (connection, dsn):
        _original(connection, scope, snapshot)
        _absent(connection, scope.replacement)
        _absent(connection, scope.failed)
        connection.execute(
            sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING {} LC_COLLATE {} LC_CTYPE {}").format(
                sql.Identifier(scope.replacement),
                sql.Identifier(snapshot["owner"]),
                sql.Literal(snapshot["encoding"]),
                sql.Literal(snapshot["collate"]),
                sql.Literal(snapshot["ctype"]),
            )
        )
        _restore_program(program, backup, dsn, scope.replacement)
        require(
            file_hash(backup) == backup_hash and file_hash(program) == program_hash, "EXCHANGE_RESTORE_INPUT_CHANGED"
        )
        with connection.transaction():
            apply_metadata(connection, scope.replacement, snapshot)
            connection.execute(
                sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.replacement))
            )
        restored = capture(connection, scope.replacement)
        require(semantic(restored) == semantic(snapshot), "EXCHANGE_RESTORED_METADATA_MISMATCH")
        return {
            "schema": "first-release-new-database-restore-v1",
            "operation": scope.operation,
            "original_oid": snapshot["oid"],
            "replacement_oid": restored["oid"],
            "backup_sha256": backup_hash,
            "status": "restored_new_database",
            "admission_opened": False,
            "old_database_deleted": False,
        }


def exchange(
    scope: Scope, snapshot: dict[str, Any], restored: dict[str, Any], *, environment: dict[str, str] | None = None
) -> dict[str, Any]:
    require(
        restored.get("schema") == "first-release-new-database-restore-v1"
        and restored.get("status") == "restored_new_database"
        and restored.get("operation") == scope.operation
        and restored.get("original_oid") == snapshot["oid"],
        "EXCHANGE_RESTORE_RECEIPT",
    )
    with control(scope, environment) as (connection, _):
        with connection.transaction():
            connection.execute("SET LOCAL lock_timeout='2s'")
            _original(connection, scope, snapshot)
            _absent(connection, scope.failed)
            target = capture(connection, scope.replacement)
            require(
                target["oid"] == restored["replacement_oid"] and semantic(target) == semantic(snapshot),
                "EXCHANGE_REPLACEMENT_IDENTITY_CHANGED",
            )
            rows = connection.execute(
                "SELECT d.datname,d.datallowconn,(SELECT count(*) FROM pg_catalog.pg_stat_activity a "
                "WHERE a.datid=d.oid) AS connections "
                "FROM pg_catalog.pg_database d WHERE d.oid=ANY(%s)",
                ([snapshot["oid"], target["oid"]],),
            ).fetchall()
            require(
                len(rows) == 2 and all(not row["datallowconn"] and row["connections"] == 0 for row in rows),
                "EXCHANGE_REQUIRES_CLOSED_ZERO_CONNECTIONS",
            )
            connection.execute(
                sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    sql.Identifier(scope.original), sql.Identifier(scope.failed)
                )
            )
            connection.execute(
                sql.SQL("ALTER DATABASE {} RENAME TO {}").format(
                    sql.Identifier(scope.replacement), sql.Identifier(scope.original)
                )
            )
            apply_metadata(connection, scope.original, snapshot)
        return {
            "status": "exchanged_closed",
            "operation": scope.operation,
            "original_oid": snapshot["oid"],
            "current_oid": target["oid"],
            "failed_database": scope.failed,
            "admission_opened": False,
            "old_database_deleted": False,
            "production": False,
        }


def seal(scope: Scope, snapshot: dict[str, Any], *, environment: dict[str, str] | None = None) -> dict[str, Any]:
    with control(scope, environment) as (connection, _):
        _original(connection, scope, snapshot)
        connection.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.original)))
        row = connection.execute(
            "SELECT count(*) AS n FROM pg_catalog.pg_stat_activity WHERE datid=%s", (snapshot["oid"],)
        ).fetchone()
        require(row["n"] == 0, "EXCHANGE_CLIENTS_REMAIN_DATABASE_KEPT_CLOSED")
    return {"status": "closed_zero_connections", "database_oid": snapshot["oid"], "admission_opened": False}


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("capture", "restore", "seal", "exchange"))
    parser.add_argument("--operation", required=True)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--admin-env-file", type=Path)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--metadata-sha256")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--backup-sha256")
    parser.add_argument("--pg-restore", type=Path)
    parser.add_argument("--pg-restore-sha256")
    parser.add_argument("--restore-receipt", type=Path)
    parser.add_argument("--restore-receipt-sha256")
    parser.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        scope = Scope(args.operation, args.local_drill)
        environment = _environment(scope, args.admin_env_file)
        ordinary(args.output.parent, directory=True)
        require(not os.path.lexists(args.output), "EXCHANGE_NEW_OUTPUT_REQUIRED")
        result = _execute(args, scope, environment)
        write_private(args.output, result)
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "NATIVE_EXCHANGE_STOP_PRESERVE_ALL", "automatic_retry": False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


def _execute(args: Any, scope: Scope, environment: dict[str, str] | None) -> dict[str, Any]:
    if args.action == "capture":
        return capture_to(scope, args.metadata, environment=environment)
    require(
        digest(args.metadata_sha256) and file_hash(args.metadata) == args.metadata_sha256, "EXCHANGE_METADATA_CHANGED"
    )
    snapshot = read_json(args.metadata)
    if args.action == "seal":
        return seal(scope, snapshot, environment=environment)
    if args.action == "restore":
        require(
            args.backup and args.pg_restore and args.backup_sha256 and args.pg_restore_sha256,
            "EXCHANGE_RESTORE_ARGUMENTS",
        )
        return restore_new(
            scope,
            snapshot,
            args.backup,
            args.backup_sha256,
            args.pg_restore,
            args.pg_restore_sha256,
            environment=environment,
        )
    require(
        args.restore_receipt
        and digest(args.restore_receipt_sha256)
        and file_hash(args.restore_receipt) == args.restore_receipt_sha256,
        "EXCHANGE_RECEIPT_CHANGED",
    )
    return exchange(scope, snapshot, read_json(args.restore_receipt), environment=environment)


def _environment(scope: Scope, path: Path | None) -> dict[str, str] | None:
    require(scope.local_drill or path is not None, "EXCHANGE_PROTECTED_ADMIN_FILE_REQUIRED")
    if path is None:
        return None
    from tools.first_release_hermes_entry import _parse_environment, _private_read

    values = _parse_environment(_private_read(path))
    require(set(values) == {"FIRST_RELEASE_EXCHANGE_ADMIN_DSN"}, "EXCHANGE_ADMIN_FILE_FIELDS")
    return values


if __name__ == "__main__":
    raise SystemExit(main())

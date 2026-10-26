"""One-shot F copy migration/backfill/replay; original stage is never a mutation target."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from psycopg import sql
from psycopg.conninfo import make_conninfo

from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.backfill import backfill
from mingjing_core.repositories.foundation import migration_manifest, validate_history
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.runtime import LangGraphRuntime
from tools.deploy_core import apply_withdrawals, export_withdrawals
from tools.first_release_contracts import (
    MIGRATIONS,
    RestoreRejected,
    ordinary,
    read_json,
    require,
)
from tools.first_release_database_metadata import capture
from tools.first_release_native_exchange import (
    _environment,
    control,
    file_hash,
    write_private,
)
from tools.first_release_replay_effects import snapshot
from tools.first_release_restore import SafeParser
from tools.first_release_stage_copy import CopyScope
from tools.first_release_writer_fence import file_lock


def checked_copy(connection, scope: CopyScope, receipt: dict) -> dict:
    require(
        receipt.get("schema") == "first-release-stage-copy-v1"
        and receipt.get("status") == "copied_closed"
        and receipt.get("operation") == scope.operation
        and receipt.get("source") == scope.source
        and receipt.get("target") == scope.target
        and receipt.get("source_readonly") is True
        and receipt.get("admission_opened") is False,
        "STAGE_COPY_RECEIPT_REQUIRED",
    )
    source, target = (
        capture(connection, scope.source),
        capture(connection, scope.target),
    )
    require(
        source["oid"] == receipt.get("source_oid") and target["oid"] == receipt.get("target_oid"),
        "STAGE_COPY_IDENTITY_CHANGED",
    )
    row = connection.execute(
        "SELECT NOT datallowconn AS closed,"
        "(SELECT count(*) FROM pg_stat_activity WHERE datid=d.oid) AS clients "
        "FROM pg_database d WHERE datname=%s",
        (scope.target,),
    ).fetchone()
    require(
        row and row["closed"] and row["clients"] == 0,
        "STAGE_NEW_COPY_CLOSED_ZERO_REQUIRED",
    )
    require(
        re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", target["owner"]),
        "STAGE_SAFE_OWNER_REQUIRED",
    )
    return target


def _history(repo: PostgresRepository) -> dict:
    with repo.connection() as connection:
        rows = connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
    return {row["version"]: row["checksum"] for row in rows}


def _counts(result: dict) -> dict:
    # Backfill sample identifiers and private payloads stay out of the public receipt.
    return {key: value for key, value in result.items() if type(value) is int}


def _prepare(repo: PostgresRepository, workspace: Path) -> dict:
    expected = migration_manifest()
    require(
        expected == {int(key): value for key, value in MIGRATIONS.items()},
        "STAGE_EXACT_MIGRATIONS_1_8",
    )
    before = _history(repo)
    validate_history(before, expected, complete=False)
    require(4 <= len(before) <= 8, "STAGE_REVIEWED_PREFIX_4_8_REQUIRED")
    repo.initialize()
    repo.verify_schema()
    LangGraphRuntime(repo)
    memory = MemoryService(repo)
    dry, first, second = (backfill(memory, "primary", apply=apply) for apply in (False, True, True))
    require(
        all(second[key] == 0 for key in ("message_metadata", "search_tokens", "assistant_created")),
        "STAGE_BACKFILL_REPEAT_CHANGED",
    )
    document = export_withdrawals(repo)
    write_private(workspace / "copy-withdrawals.json", document)
    replay = apply_withdrawals(repo, document)
    after = snapshot(repo)
    repeat = apply_withdrawals(repo, document)
    require(snapshot(repo) == after, "STAGE_REPLAY_REPEAT_CHANGED")
    return {
        "migrations_applied": sorted(set(expected) - set(before)),
        "migration_checksums": {str(key): value for key, value in _history(repo).items()},
        "backfill_dry_run": _counts(dry),
        "backfill_apply": _counts(first),
        "backfill_repeat": _counts(second),
        "replay": replay,
        "replay_repeat": repeat,
        "replay_full_state_unchanged": True,
        "withdrawals_sha256": file_hash(workspace / "copy-withdrawals.json"),
    }


def prepare_copy(scope: CopyScope, workspace: Path, receipt: dict, *, environment=None) -> dict:
    scope.validate()
    ordinary(workspace, directory=True)
    require(
        scope.local_drill or workspace.stat().st_mode & 0o077 == 0,
        "STAGE_PRIVATE_WORKSPACE",
    )
    with file_lock(workspace / "writer.lock", exclusive=True), control(scope, environment) as (admin, dsn):
        require(
            not any(os.path.lexists(workspace / name) for name in ("prepare-started.json", "prepare-receipt.json")),
            "STAGE_PREPARE_ALREADY_STARTED_NO_RETRY",
        )
        target = checked_copy(admin, scope, receipt)
        original = capture(admin, scope.source)
        write_private(
            workspace / "prepare-started.json",
            {"operation": scope.operation, "target_oid": target["oid"]},
        )
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS true").format(sql.Identifier(scope.target)))
        # A fixed identifier-only role option ensures new SQL objects belong to the preserved owner.
        repo = PostgresRepository(
            make_conninfo(
                dsn,
                dbname=scope.target,
                options="-c role=" + target["owner"] + " -c search_path=public,pg_catalog",
            ),
            initialize=False,
            max_size=2,
        )
        try:
            result = _prepare(repo, workspace)
        finally:
            repo.close()
        admin.execute(sql.SQL("ALTER DATABASE {} ALLOW_CONNECTIONS false").format(sql.Identifier(scope.target)))
        require(
            admin.execute(
                "SELECT count(*) AS n FROM pg_stat_activity WHERE datid=%s",
                (target["oid"],),
            ).fetchone()["n"]
            == 0,
            "STAGE_PREPARED_COPY_CLIENTS_REMAIN_CLOSED",
        )
        require(
            capture(admin, scope.source) == original,
            "STAGE_SOURCE_METADATA_CHANGED",
        )
    result.update(
        schema="first-release-stage-prepare-v1",
        status="prepared_closed",
        operation=scope.operation,
        database=scope.target,
        target_oid=target["oid"],
        admission_opened=False,
        model_calls=0,
        external_sends=0,
        automatic_retry=False,
    )
    write_private(workspace / "prepare-receipt.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = SafeParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--copy-receipt", type=Path, required=True)
    parser.add_argument("--copy-receipt-sha256", required=True)
    parser.add_argument("--admin-env-file", type=Path)
    parser.add_argument("--local-drill", action="store_true")
    parser.add_argument("--apply", action="store_true")
    try:
        args = parser.parse_args(argv)
        scope = CopyScope(args.operation, args.local_drill)
        scope.validate()
        if not args.apply:
            print(
                json.dumps(
                    {
                        "status": "arguments_validated",
                        "database_connections": 0,
                        "model_calls": 0,
                    }
                )
            )
            return 0
        require(
            file_hash(args.copy_receipt) == args.copy_receipt_sha256,
            "STAGE_COPY_RECEIPT_CHANGED",
        )
        result = prepare_copy(
            scope,
            args.workspace,
            read_json(args.copy_receipt),
            environment=_environment(scope, args.admin_env_file),
        )
    except RestoreRejected as error:
        print(json.dumps({"status": "blocked", "code": str(error), "automatic_retry": False}))
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "STAGE_PREPARE_STOP_PRESERVE_ALL",
                    "automatic_retry": False,
                }
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

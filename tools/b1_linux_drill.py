"""Retained local Docker PG15 rehearsal; never SSH, delete or start application writers."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import get_clock
from tools.b1_linux_drill_sql import (
    DATABASES,
    apply_sql,
    fixture_sql,
    grants,
    immutable_snapshot_sql,
    migrations,
    owner_sql,
    permission_sql,
    public_rows,
    schema_snapshot_sql,
)
from tools.b1_linux_drill_transport import (
    CONTAINER,
    VOLUMES,
    DrillBlocked,
    LocalDocker,
    require,
)
from tools.core_incremental_contracts import MIGRATIONS, TARGET

MIGRATION8_SHA256 = "5eef5d65363baa0ab4dc8ec9763b85136f4ba249688330b9cd8448f0b39ccbcb"


def plan(mode: str = "full-sql") -> dict[str, Any]:
    require(mode in {"full-sql", "storage-preparation"}, "DRILL_MODE")
    value = {
        "schema": "b1-linux-drill-plan-v1",
        "target": TARGET,
        "container": CONTAINER,
        "retained_volumes": list(VOLUMES),
        "databases": list(DATABASES),
        "b1_migrations": list(range(1, 8)),
        "ledger_0008": "separate-compatibility-only-not-in-B1",
        "schema4_backup_restore": True,
        "rollback": "restore-same-dump-into-separate-new-database",
        "application_backfill": "not-exercised-by-this-SQL-drill",
        "server_connections": 0,
        "model_calls": 0,
        "external_sends": 0,
        "removes_existing_objects": False,
        "starts_business_services": False,
    }
    if mode == "storage-preparation":
        value.update(
            mode=mode,
            restores_database=False,
            restore_target_reserved_empty=True,
            formal_restore_proof=False,
            application_runtime_required=True,
        )
    return value


def create_databases(docker: LocalDocker) -> None:
    existing = json.loads(
        docker.sql(
            "b1_drill_control",
            "SELECT coalesce(json_agg(datname),'[]') FROM pg_database;",
        )
    )
    require(
        not set(DATABASES).intersection(existing),
        "DRILL_DATABASE_ALREADY_EXISTS_NO_AUTOMATIC_REPLAY",
    )
    for database in DATABASES:
        owner = database + "_owner" if database.startswith("zhiming_core_") else "b1_drill_admin"
        if owner != "b1_drill_admin":
            writer = database + "_writer"
            docker.sql(
                "b1_drill_control",
                f"CREATE ROLE {owner} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT; "
                f"CREATE ROLE {writer} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;",
            )
        docker.sql("b1_drill_control", f"CREATE DATABASE {database} OWNER {owner};")
        docker.sql(database, "REVOKE CREATE ON SCHEMA public FROM PUBLIC;")
        if database in {"zhiming_core_stage", "b1_drill_ledger"}:
            docker.sql(database, f"CREATE SCHEMA mingjing_core AUTHORIZATION {owner};")


def restore(docker: LocalDocker, target: str, dump: str) -> None:
    require(
        target in {"zhiming_core_b1_restore", "b1_drill_rollback"},
        "RESTORE_TARGET_NOT_ISOLATED",
    )
    role = target + "_owner" if target.startswith("zhiming_core_") else "b1_drill_admin"
    docker.execute(
        [
            "pg_restore",
            "--host=127.0.0.1",
            "--port=5432",
            "--username=" + role,
            "--no-owner",
            "--no-acl",
            "--exit-on-error",
            "--dbname=" + target,
            dump,
        ]
    )


def check_permissions(docker: LocalDocker, database: str) -> dict[str, Any]:
    value = json.loads(docker.sql(database, permission_sql(), role=database + "_writer"))
    for key in (
        "superuser",
        "createdb",
        "createrole",
        "bypassrls",
        "database_create",
        "schema_create",
        "public_create",
        "ledger_write",
    ):
        require(value.get(key) is False, "WRITER_ELEVATED_OR_LEDGER_WRITABLE")
    require(
        value.get("ledger_select") is True and value.get("tables") and all(value["tables"].values()),
        "WRITER_TABLE_GRANTS_MISSING",
    )
    return value


def migrate_restore(docker: LocalDocker, rows: list[dict[str, Any]], baseline: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for database in ("zhiming_core_stage", "zhiming_core_b1_restore"):
        owner = database + "_owner"
        docker.sql(database, apply_sql(rows[4:]), role=owner)
        docker.sql(database, grants(database), role=owner)
        ledger = json.loads(docker.sql(database, schema_snapshot_sql(), role=owner))
        require(
            ledger["version"] == 7 and ledger["checksums"] == MIGRATIONS,
            "MIGRATION_LEDGER_MISMATCH",
        )
        unchanged = json.loads(docker.sql(database, immutable_snapshot_sql(), role=owner))
        require(unchanged == baseline, "IMMUTABLE_FIXTURE_CHANGED")
        ownership = json.loads(docker.sql(database, owner_sql(), role=owner))
        require(
            ownership["schema"] == owner and ownership["relations"] and set(ownership["relations"].values()) == {owner},
            "MIGRATION_OWNER_MISMATCH",
        )
        result[database] = {
            "ledger": ledger,
            "immutable_preserved": True,
            "ownership": ownership,
            "writer_permissions": check_permissions(docker, database),
        }
    return result


def ledger_compatibility(docker: LocalDocker, migration8: Path | None) -> dict[str, Any]:
    if migration8 is None:
        return {
            "executed": False,
            "reason": "explicit-P1b-0008-source-required",
            "part_of_B1": False,
        }
    require(
        migration8.name == "0008_model_usage.sql" and migration8.is_file(),
        "SEPARATE_LEDGER_SOURCE_REQUIRED",
    )
    source = migration8.read_bytes().replace(b"\r\n", b"\n")
    require(
        hashlib.sha256(source).hexdigest() == MIGRATION8_SHA256,
        "P1B_LEDGER_HASH_MISMATCH",
    )
    docker.sql(
        "b1_drill_ledger",
        "BEGIN; SET LOCAL search_path TO mingjing_core;\n" + source.decode() + "\nCOMMIT;",
    )
    count = int(
        docker.sql(
            "b1_drill_ledger",
            "SELECT count(*) FROM pg_tables WHERE schemaname='mingjing_core';",
        )
    )
    require(count == 4, "P1B_LEDGER_TABLE_COUNT")
    return {
        "executed": True,
        "part_of_B1": False,
        "sha256": hashlib.sha256(source).hexdigest(),
        "tables": count,
    }


def backup_stage(docker: LocalDocker, run_id: str) -> tuple[str, str, str]:
    directory = "/b1/" + run_id
    docker.execute(["install", "-d", "-m", "0700", directory])
    dump = directory + "/schema4.dump"
    docker.execute(
        [
            "pg_dump",
            "--host=127.0.0.1",
            "--port=5432",
            "--username=zhiming_core_stage_owner",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            "--file=" + dump,
            "zhiming_core_stage",
        ]
    )
    docker.execute(["chmod", "0600", dump])
    dump_hash = docker.execute(["sha256sum", dump]).decode().split()[0]
    require(re.fullmatch(r"[a-f0-9]{64}", dump_hash), "DUMP_HASH_INVALID")
    return directory, dump, dump_hash


def check_rollback(docker: LocalDocker, dump: str, baseline: dict[str, Any]) -> None:
    restore(docker, "b1_drill_rollback", dump)
    rollback = json.loads(docker.sql("b1_drill_rollback", immutable_snapshot_sql()))
    rollback_ledger = json.loads(docker.sql("b1_drill_rollback", schema_snapshot_sql()))
    require(
        rollback == baseline
        and rollback_ledger["version"] == 4
        and rollback_ledger["checksums"] == {key: value for key, value in MIGRATIONS.items() if int(key) <= 4},
        "ROLLBACK_RESTORE_MISMATCH",
    )


def metrics(docker: LocalDocker, directory: str, dump: str) -> dict[str, Any]:
    sizes = {
        database: int(docker.sql(database, "SELECT pg_database_size(current_database());")) for database in DATABASES
    }
    modes = docker.execute(["stat", "--format=%a", directory, dump]).decode().splitlines()
    require(modes == ["700", "600"], "LINUX_BACKUP_MODE")
    return {"database_sizes_bytes": sizes, "backup_modes": modes}


def execute(
    repo: Path, docker: LocalDocker, *, run_id: str, pull: bool, migration8: Path | None, mode: str = "full-sql"
) -> dict[str, Any]:
    require(re.fullmatch(r"b1-[a-z0-9-]{8,60}", run_id), "DRILL_OPERATION_ID")
    plan(mode)
    rows = migrations(repo)
    identity = docker.verify_local()
    image = docker.image(pull=pull)
    resources = docker.create_container(image)
    docker.wait_postgres()
    version = int(docker.sql("b1_drill_control", "SELECT current_setting('server_version_num');"))
    require(150000 <= version < 160000, "POSTGRES15_REQUIRED")
    create_databases(docker)
    docker.sql("zhiming_core_stage", apply_sql(rows[:4]), role="zhiming_core_stage_owner")
    docker.sql("zhiming_core_stage", fixture_sql(), role="zhiming_core_stage_owner")
    baseline = json.loads(docker.sql("zhiming_core_stage", immutable_snapshot_sql()))
    directory, dump, dump_hash = backup_stage(docker, run_id)
    if mode == "storage-preparation":
        from tools.b1_linux_application_drill_storage import preparation

        return dict(
            preparation(docker, run_id=run_id, directory=directory, dump=dump, dump_hash=dump_hash),
            engine=identity,
            image=image,
            resources=resources,
            server_version_num=version,
        )
    restore(docker, "zhiming_core_b1_restore", dump)
    after = migrate_restore(docker, rows, baseline)
    check_rollback(docker, dump, baseline)
    compatibility = ledger_compatibility(docker, migration8)
    return {
        **plan(),
        "schema": "b1-linux-drill-result-v1",
        "status": "pg-migration-slice-passed",
        "at": get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "engine": identity,
        "image": image,
        "resources": resources,
        "server_version_num": version,
        "run_id": run_id,
        "migration_source": public_rows(rows),
        "dump_sha256": dump_hash,
        "upgraded": after,
        "rollback_schema4": True,
        "ledger_0008": compatibility,
        **metrics(docker, directory, dump),
        "native_host_switch": "not-verified",
        "B7_replay": "separate-reviewed-entry-required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--mode", choices=("full-sql", "storage-preparation"), default="full-sql")
    parser.add_argument("--pull-postgres15", action="store_true")
    parser.add_argument("--run-id", default="b1-20261021-local")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--p1b-migration8", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if not args.apply:
            print(json.dumps(plan(args.mode), ensure_ascii=False))
            return 0
        require(
            args.output is not None and not args.output.exists(),
            "NEW_RECEIPT_PATH_REQUIRED",
        )
        result = execute(
            args.repo,
            LocalDocker(),
            run_id=args.run_id,
            pull=args.pull_postgres15,
            migration8=args.p1b_migration8,
            mode=args.mode,
        )
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "receipt": str(args.output),
                    "publication": False,
                }
            )
        )
        return 0
    except DrillBlocked as error:
        print(json.dumps({"ok": False, "code": error.code, "publication": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Preserve an empty B3 target; this storage receipt is never an application proof."""

from __future__ import annotations

import json
from typing import Any

from tools.b1_linux_drill_sql import schema_snapshot_sql
from tools.b1_linux_drill_transport import LocalDocker, require
from tools.core_incremental_contracts import EXPECTED_MANIFEST, MIGRATIONS, TARGET, digest


def source_state(docker: LocalDocker) -> str:
    tables = json.loads(
        docker.sql(
            "zhiming_core_stage",
            "SELECT coalesce(json_agg(t),'[]') FROM "
            "(SELECT schemaname,tablename FROM pg_tables WHERE schemaname='mingjing_core' OR schemaname='public' "
            "AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes','checkpoint_migrations') "
            "ORDER BY schemaname,tablename)t;",
        )
    )
    hashes = {}
    for row in tables:
        namespace, table = row["schemaname"], row["tablename"]
        require(namespace in {"mingjing_core", "public"} and table.replace("_", "a").isalnum(), "STORAGE_TABLE_SCOPE")
        hashes[namespace + "." + table] = docker.sql(
            "zhiming_core_stage",
            "SELECT encode(sha256(convert_to("
            "coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text,'UTF8')),'hex') "
            f'FROM "{namespace}"."{table}" t;',
        )
    require(hashes, "STORAGE_SOURCE_EMPTY")
    return digest(hashes)


def preparation(docker: LocalDocker, *, run_id: str, directory: str, dump: str, dump_hash: str) -> dict[str, Any]:
    ledger = json.loads(docker.sql("zhiming_core_stage", schema_snapshot_sql()))
    expected = {str(key): MIGRATIONS[str(key)] for key in range(1, 5)}
    require(ledger == {"version": 4, "checksums": expected}, "STORAGE_SCHEMA4_CHECKSUMS")
    empty = int(
        docker.sql(
            "zhiming_core_b1_restore",
            "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n "
            "ON n.oid=c.relnamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
            "AND n.nspname NOT LIKE 'pg_toast%')+(SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
            "ON n.oid=p.pronamespace WHERE n.nspname NOT IN ('pg_catalog','information_schema'));",
        )
    )
    require(empty == 0, "B3_RESTORE_TARGET_NOT_EMPTY")
    modes = docker.execute(["stat", "--format=%a", directory, dump]).decode().splitlines()
    require(modes == ["700", "600"], "LINUX_BACKUP_MODE")
    checkpoint_count = int(
        docker.sql(
            "zhiming_core_stage",
            "SELECT count(*) FROM pg_tables WHERE "
            "schemaname='public' AND tablename IN "
            "('checkpoints','checkpoint_blobs','checkpoint_writes','checkpoint_migrations');",
        )
    )
    return {
        "schema": "b1-linux-storage-preparation-v1",
        "status": "storage-prepared-application-blocked",
        "operation_id": run_id,
        "target": TARGET,
        "manifest_sha256": EXPECTED_MANIFEST,
        "source_database": "zhiming_core_stage",
        "source_schema": 4,
        "checksums": ledger["checksums"],
        "source_state_sha256": source_state(docker),
        "dump_path": dump,
        "dump_sha256": dump_hash,
        "backup_modes": modes,
        "restore_database": "zhiming_core_b1_restore",
        "restore_target_empty": True,
        "restore_written": False,
        "checkpoint_tables": checkpoint_count,
        "application_ready": False,
        "admissible_restore_proof": False,
        "publication": False,
        "model_calls": 0,
        "external_sends": 0,
        "blockers": [
            "LINUX_CORE_RUNTIME_NOT_VERIFIED",
            "B2_LEDGER_NOT_EXPORTED",
            *(["CHECKPOINT_BOOTSTRAP_NOT_RUN"] if checkpoint_count != 4 else []),
        ],
    }

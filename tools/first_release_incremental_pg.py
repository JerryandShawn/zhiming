"""Observed local capture: cooperative fences, one MVCC snapshot, and fresh-state drift checks."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.first_release_contracts import RestoreRejected, ordinary, require
from tools.first_release_incremental import HERE, BackupInputs, file_hash
from tools.first_release_writer_fence import file_lock, pg_lock

CHECKPOINTS = ("checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations")
BOOTSTRAP = """import hashlib,json,pathlib,runpy,sys
value=json.loads(sys.stdin.readline())
path=pathlib.Path(value['worker'])
if hashlib.sha256(path.read_bytes()).hexdigest()!=value['controls']['first_release_incremental_worker.py']:
    raise SystemExit(2)
runpy.run_path(str(path),run_name='__main__',init_globals={'_INCREMENTAL_INPUT':value})
"""


def readonly(dsn: str) -> str:
    return make_conninfo(dsn, options="-c default_transaction_read_only=on -c search_path=pg_catalog")


def identity(connection: Any, inputs: BackupInputs, role: str) -> int:
    row = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version,pg_backend_pid() AS pid,"
        "(SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,"
        "(SELECT oid FROM pg_roles WHERE rolname=current_user) AS role_oid"
    ).fetchone()
    require(
        row["role"] == row["session_role"] == inputs.source.database + "_" + role
        and row["database"] == inputs.source.database
        and row["database_oid"] == inputs.source.database_oid,
        "INCREMENTAL_ACTUAL_SOURCE_IDENTITY",
    )
    require(
        row["role_oid"] == getattr(inputs.source, role + "_oid") and 150000 <= row["version"] < 160000,
        "INCREMENTAL_ACTUAL_SOURCE_ROLE",
    )
    require(
        (row["host"], row["port"]) == (connection.info.host, connection.info.port),
        "INCREMENTAL_ACTUAL_SOURCE_LOCATION",
    )
    return row["pid"]


def admin_identity(connection: Any, inputs: BackupInputs, fields: dict[str, str]) -> int:
    row = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version,pg_backend_pid() AS pid,"
        "(pg_control_system()).system_identifier::text AS system_identifier"
    ).fetchone()
    require(
        (
            row["database"],
            row["role"],
            row["session_role"],
            row["host"],
            str(row["port"]),
        )
        == (
            fields["dbname"],
            fields["user"],
            fields["user"],
            fields["host"],
            fields["port"],
        )
        and 150000 <= row["version"] < 160000
        and row["system_identifier"] == inputs.source.system_identifier,
        "INCREMENTAL_ACTUAL_SERVER_IDENTITY",
    )
    expected = [
        (inputs.source.database + "_" + role, getattr(inputs.source, role + "_oid")) for role in ("owner", "writer")
    ]
    roles = connection.execute(
        "SELECT rolname,oid,rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR "
        "rolbypassrls OR rolinherit OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) AS unsafe "
        "FROM pg_roles WHERE rolname=ANY(%s)",
        ([item[0] for item in expected],),
    ).fetchall()
    require(
        sorted((role["rolname"], role["oid"]) for role in roles) == expected
        and not any(role["unsafe"] for role in roles),
        "INCREMENTAL_SOURCE_ROLES_UNSAFE",
    )
    database = connection.execute(
        "SELECT oid,datdba FROM pg_database WHERE datname=%s", (inputs.source.database,)
    ).fetchone()
    require(
        database == {"oid": inputs.source.database_oid, "datdba": inputs.source.owner_oid},
        "INCREMENTAL_SOURCE_DATABASE_OID",
    )
    return row["pid"]


def sessions(connection: Any, allowed: set[int]) -> None:
    connection.execute("SELECT pg_stat_clear_snapshot()")
    actual = connection.execute("SELECT pid FROM pg_stat_activity WHERE datname=current_database()").fetchall()
    require({row["pid"] for row in actual} == allowed, "INCREMENTAL_OTHER_SOURCE_SESSION")


def source_scope(connection: Any, inputs: BackupInputs) -> None:
    history = connection.execute(
        "SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version"
    ).fetchall()
    require(
        {str(row["version"]): row["checksum"] for row in history} == dict(inputs.source.migrations),
        "INCREMENTAL_ACTUAL_SOURCE_PREFIX",
    )
    owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
    require(owners == list(inputs.source.owners), "INCREMENTAL_ACTUAL_OWNER_SET")
    counts = connection.execute(
        "SELECT count(*) FILTER(WHERE status IN ('queued','running') OR lease_until>now()) "
        "AS busy FROM mingjing_core.core_runs"
    ).fetchone()
    require(counts["busy"] == 0, "INCREMENTAL_ACTIVE_RUN_OR_LEASE")
    objects = connection.execute(
        "SELECT n.nspname,c.relname,c.relkind, c.relowner FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public') "
        "AND c.relkind IN ('r','p','S','v','m','f')"
    ).fetchall()
    require(
        objects and all(row["relowner"] == inputs.source.owner_oid for row in objects),
        "INCREMENTAL_OBJECT_OWNER",
    )
    require(
        not any(row["relname"].startswith("core_model_") and row["relname"] != "core_model_charges" for row in objects),
        "INCREMENTAL_CENTRAL_RELATION_REJECTED",
    )
    require(
        all(
            row["relkind"] in {"r", "S"} and (row["nspname"] == "mingjing_core" or row["relname"] in CHECKPOINTS)
            for row in objects
        ),
        "INCREMENTAL_SOURCE_RELATION_PROFILE",
    )


def snapshot(connection: Any) -> dict[str, dict[str, Any]]:
    connection.execute("SET LOCAL TimeZone='UTC'")
    require(
        connection.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS, "INCREMENTAL_SNAPSHOT_TX_REQUIRED"
    )
    result = {"tables": {}, "sequences": {}, "columns": {}}
    rows = connection.execute(
        "SELECT n.nspname,c.relname,c.relkind,c.oid FROM pg_class c JOIN pg_namespace n "
        "ON n.oid=c.relnamespace WHERE (n.nspname='mingjing_core' OR n.nspname='public' AND c.relname=ANY(%s)) "
        "AND c.relkind IN ('r','S') ORDER BY n.nspname,c.relname",
        (list(CHECKPOINTS),),
    ).fetchall()
    for row in rows:
        if row["relkind"] == "S":
            query = sql.SQL("SELECT last_value,log_cnt,is_called FROM {}")
            result["sequences"][row["nspname"] + "." + row["relname"]] = dict(
                connection.execute(query.format(sql.Identifier(row["nspname"], row["relname"]))).fetchone()
            )
            continue
        result["columns"][row["nspname"] + "." + row["relname"]] = connection.execute(
            "SELECT attname AS name,format_type(atttypid,atttypmod) AS type,attnotnull AS not_null "
            "FROM pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped ORDER BY attnum",
            (row["oid"],),
        ).fetchall()
        query = sql.SQL(
            "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) "
            "ORDER BY to_jsonb(t)::text COLLATE \"C\"),'[]'::jsonb)::text,'UTF8')),'hex') AS value FROM {} t"
        )
        result["tables"][row["nspname"] + "." + row["relname"]] = connection.execute(
            query.format(sql.Identifier(row["nspname"], row["relname"]))
        ).fetchone()["value"]
    return result


def environment(dsn: str) -> dict[str, str]:
    result = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR", "TEMP", "TMP") if key in os.environ}
    result.update(
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        CORE_FEISHU_ENABLED="false",
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
    )
    fields = conninfo_to_dict(dsn)
    if fields.get("password"):
        result["PGPASSWORD"] = fields["password"]
    result["PGPASSFILE"] = os.devnull
    return result


def dump(inputs: BackupInputs, dsn: str, snapshot_id: str) -> None:
    require(
        file_hash(inputs.pg_dump) == inputs.pg_dump_sha256,
        "INCREMENTAL_REVIEWED_PROGRAM_CHANGED",
    )
    env, fields = environment(dsn), conninfo_to_dict(dsn)
    version = subprocess.run([str(inputs.pg_dump), "--version"], env=env, capture_output=True, timeout=10)
    require(
        version.returncode == 0 and re.search(rb"PostgreSQL\) 15\.[0-9]+", version.stdout),
        "INCREMENTAL_PG_DUMP15_REQUIRED",
    )
    command = [
        str(inputs.pg_dump),
        "--host=" + fields["host"],
        "--port=" + fields["port"],
        "--username=" + fields["user"],
        "--dbname=" + fields["dbname"],
        "--no-password",
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--snapshot=" + snapshot_id,
    ]
    path = inputs.operation_dir / "backup.dump"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w+b") as stream:
        result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.PIPE, timeout=180)
        require(result.returncode == 0, "INCREMENTAL_PG_DUMP_FAILED_OUTPUT_RETAINED")
        stream.flush()
        os.fsync(stream.fileno())
        stream.seek(0)
        require(stream.read(5) == b"PGDMP", "INCREMENTAL_CUSTOM_DUMP_REQUIRED")


def read_handshake(process: Any) -> dict[str, Any]:
    messages: queue.Queue[str] = queue.Queue(maxsize=1)
    threading.Thread(target=lambda: messages.put(process.stdout.readline()), daemon=True).start()
    try:
        value = json.loads(messages.get(timeout=30))
        require(
            isinstance(value, dict)
            and set(value) == {"schema", "pid"}
            and value["schema"] == "first-release-incremental-export-handshake-v1"
            and type(value["pid"]) is int
            and value["pid"] > 0,
            "INCREMENTAL_WORKER_HANDSHAKE",
        )
        return value
    except (queue.Empty, ValueError, TypeError):
        raise RestoreRejected("INCREMENTAL_WORKER_HANDSHAKE") from None


def candidate_export(inputs: BackupInputs, dsn: str, connection: Any, snapshot_id: str) -> dict[str, Any]:
    payload = {
        "worker": str(HERE / "first_release_incremental_worker.py"),
        "controls": dict(inputs.controls),
        "foundation": str(HERE / "first_release_replay_worker.py"),
        "root": str(inputs.candidate_source),
        "python": str(inputs.python),
        "pin": {
            "candidate": inputs.release.candidate,
            "manifest_sha256": inputs.release.manifest_sha256,
            "python_sha256": inputs.python_sha256,
        },
        "core_lock_sha256": dict(inputs.release.locks)["requirements-core.lock"],
        "source": asdict(inputs.source),
        "snapshot": snapshot_id,
    }
    env = environment("")
    env.pop("PGPASSFILE")
    env["FIRST_INCREMENTAL_OWNER_DSN"] = dsn
    process = subprocess.Popen(
        [
            str(inputs.python),
            "-I",
            "-B",
            "-X",
            "pycache_prefix=" + os.path.abspath(os.devnull),
            "-c",
            BOOTSTRAP,
        ],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()
        handshake = read_handshake(process)
        sessions(connection, {connection.info.backend_pid, handshake["pid"]})
        output, _ = process.communicate(json.dumps({"pid": handshake["pid"]}) + "\n", timeout=120)
        require(process.returncode == 0, "INCREMENTAL_CANDIDATE_EXPORT_FAILED")
        result = json.loads(output)
        require(
            isinstance(result, dict)
            and result.get("schema") == "first-release-incremental-export-v1"
            and result.get("pid") == handshake["pid"]
            and result.get("snapshot") == snapshot_id,
            "INCREMENTAL_CANDIDATE_EXPORT_RECEIPT",
        )
        return result
    finally:
        if process.poll() is None:
            process.kill()  # Only this exact newly spawned helper, never a PG backend or another service.
        process.communicate()


def write_private(path: Path, document: dict[str, Any]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())


def capture_lineage(inputs: BackupInputs) -> dict[str, Any]:
    return {
        "operation_id": inputs.operation_id,
        "manifest_sha256": inputs.release.manifest_sha256,
        "locks": dict(inputs.release.locks),
        "source": json.loads(json.dumps(asdict(inputs.source))),
        "python_sha256": inputs.python_sha256,
        "pg_dump_sha256": inputs.pg_dump_sha256,
        "controls": dict(inputs.controls),
    }


def capture(inputs: BackupInputs, dsns: dict[str, str], connection: Any) -> dict[str, Any]:
    pid = connection.info.backend_pid
    sessions(connection, {pid})
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        source_scope(connection, inputs)
        before = snapshot(connection)
        snapshot_id = connection.execute("SELECT pg_export_snapshot() AS id").fetchone()["id"]
        exported = candidate_export(inputs, dsns["owner"], connection, snapshot_id)
        write_private(inputs.operation_dir / "latest-withdrawals.json", exported["document"])
        sessions(connection, {pid})
        dump(inputs, dsns["owner"], snapshot_id)
        sessions(connection, {pid})
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        source_scope(connection, inputs)
        after = snapshot(connection)
    require(before == after, "INCREMENTAL_SOURCE_CHANGED_OUTPUTS_RETAINED")
    inputs.validate()
    return {
        "schema": "first-release-local-incremental-backup-v1",
        "candidate": inputs.release.candidate,
        "capture_lineage": capture_lineage(inputs),
        "source_projection": "postgres-jsonb-utc-v1",
        "dump_sha256": file_hash(inputs.operation_dir / "backup.dump"),
        "ledger_sha256": file_hash(inputs.operation_dir / "latest-withdrawals.json"),
        "source_state_sha256": hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest(),
        "_source_snapshots": {"before": before, "after": after},
        "global_quiescence_verified": False,
        "session_checks": "before_after",
        "same_mvcc_snapshot": True,
        "sequence_before_after_checked": True,
        "status": "local_backup_captured",
        "backup_captured": True,
        "source_upgraded": False,
        "source_restore_content_verified": False,
        "native_restore_completed": False,
        "runtime_verified": False,
        "central_binding_verified": False,
        "linux_attestation": False,
        "publication": False,
        "maintenance_retained": True,
        "model_calls": 0,
        "external_sends": 0,
    }


def backup(inputs: BackupInputs, dsns: dict[str, str]) -> dict[str, Any]:
    inputs.fence_path.parent.mkdir(parents=True, exist_ok=True)
    ordinary(inputs.fence_path.parent, directory=True)
    with file_lock(inputs.fence_path, exclusive=True):
        with psycopg.connect(readonly(dsns["admin"]), row_factory=dict_row) as admin:
            admin_identity(admin, inputs, conninfo_to_dict(dsns["admin"]))
        with psycopg.connect(readonly(dsns["writer"]), row_factory=dict_row) as writer:
            identity(writer, inputs, "writer")
        with psycopg.connect(readonly(dsns["owner"]), autocommit=True, row_factory=dict_row) as owner:
            identity(owner, inputs, "owner")
            with pg_lock(owner, inputs.fence_key, exclusive=True):
                sessions(owner, {owner.info.backend_pid})
                source_scope(owner, inputs)
                require(not inputs.maintenance.exists(), "INCREMENTAL_MAINTENANCE_ALREADY_PRESENT")
                for name in (
                    "backup.dump",
                    "latest-withdrawals.json",
                    "backup-receipt.json",
                    "backup-started.json",
                ):
                    require(
                        not os.path.lexists(inputs.operation_dir / name),
                        "INCREMENTAL_EXISTING_OUTPUT_REJECTED",
                    )
                started = {
                    "operation_id": inputs.operation_id,
                    "database_oid": inputs.source.database_oid,
                }
                write_private(inputs.maintenance, started)
                write_private(inputs.operation_dir / "backup-started.json", started)
                result = capture(inputs, dsns, owner)
                evidence = result.pop("_source_snapshots")
                write_private(
                    inputs.operation_dir / "backup-receipt.json",
                    dict(result, source_snapshots=evidence),
                )
                return result

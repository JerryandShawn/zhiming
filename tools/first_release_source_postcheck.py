"""Read-only Core8 observations for the existing synthetic source; no write capability."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql

from tools.first_release_acl import CORE_TABLES, DML, LEDGERS, QUOTA, table_acl, verify_relations
from tools.first_release_contracts import RestoreRejected, digest, require
from tools.first_release_incremental import BackupInputs
from tools.first_release_incremental_pg import sessions
from tools.first_release_source_profile import checked_identity, expected_relations, routines, triggers

USAGE_SEQUENCE = "mingjing_core.core_model_usage_id_seq"


def _transaction(connection: Any, source: BackupInputs, role: str) -> dict[str, Any]:
    require(type(source) is BackupInputs and source.local_drill is True, "SOURCE_POSTCHECK_LOCAL_TYPED_INPUT")
    source.source.validate(source.operation_id, source.release)
    require(
        isinstance(connection, psycopg.Connection)
        and not connection.closed
        and connection.autocommit
        and connection.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS,
        "SOURCE_POSTCHECK_REAL_TRANSACTION_REQUIRED",
    )
    settings = connection.execute(
        "SELECT pg_catalog.current_setting('transaction_read_only') AS ro,"
        "pg_catalog.current_setting('transaction_isolation') AS isolation,"
        "pg_catalog.current_setting('search_path') AS path,pg_catalog.current_schemas(false)::text[] AS schemas"
    ).fetchone()
    require(
        settings == {"ro": "on", "isolation": "repeatable read", "path": "pg_catalog", "schemas": ["pg_catalog"]},
        "SOURCE_POSTCHECK_READONLY_CATALOG_REQUIRED",
    )
    identity = checked_identity(connection, source, role)
    require(identity["host"] in {"127.0.0.1", "::1"}, "SOURCE_POSTCHECK_LOCAL_CONNECTION_REQUIRED")
    return identity


def _baseline(source: BackupInputs, baseline: dict[str, Any], checkpoint_versions: tuple[int, ...]) -> None:
    require(
        type(baseline) is dict
        and set(baseline) == {"tables", "sequences", "columns"}
        and all(type(value) is dict for value in baseline.values()),
        "SOURCE_POSTCHECK_BASELINE_MAPS",
    )
    require(
        set(baseline["tables"]) == set(baseline["columns"]) == expected_relations(len(source.source.migrations))
        and not baseline["sequences"]
        and all(digest(value) for value in baseline["tables"].values()),
        "SOURCE_POSTCHECK_ORIGINAL_RELATIONS",
    )
    require(
        type(checkpoint_versions) is tuple
        and all(type(version) is int for version in checkpoint_versions)
        and checkpoint_versions == tuple(range(len(checkpoint_versions))),
        "SOURCE_POSTCHECK_ORIGINAL_CHECKPOINT_VERSIONS",
    )
    for columns in baseline["columns"].values():
        require(type(columns) is list and bool(columns), "SOURCE_POSTCHECK_ORIGINAL_COLUMNS")
        require(
            all(
                type(row) is dict
                and set(row) == {"name", "type", "not_null"}
                and isinstance(row["name"], str)
                and bool(row["name"])
                and isinstance(row["type"], str)
                and bool(row["type"])
                and type(row["not_null"]) is bool
                for row in columns
            )
            and len({row["name"] for row in columns}) == len(columns),
            "SOURCE_POSTCHECK_ORIGINAL_COLUMN_FIELDS",
        )


def _original_columns(connection: Any, source: BackupInputs, name: str, columns: list[dict[str, Any]]) -> None:
    relation = connection.execute(
        "SELECT c.oid,c.relkind::text AS kind,c.relowner FROM pg_catalog.pg_class c "
        "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname||'.'||c.relname=%s",
        (name,),
    ).fetchone()
    require(
        relation and relation["kind"] == "r" and relation["relowner"] == source.source.owner_oid,
        "SOURCE_POSTCHECK_ORIGINAL_TABLE_CHANGED",
    )
    actual = connection.execute(
        "SELECT attname AS name,format_type(atttypid,atttypmod) AS type,attnotnull AS not_null "
        "FROM pg_attribute WHERE attrelid=%s AND attnum>0 AND NOT attisdropped ORDER BY attnum",
        (relation["oid"],),
    ).fetchall()
    by_name = {row["name"]: row for row in actual}
    require(all(by_name.get(row["name"]) == row for row in columns), "SOURCE_POSTCHECK_ORIGINAL_COLUMN_CHANGED")


def _projected_hash(
    connection: Any,
    source: BackupInputs,
    name: str,
    columns: list[dict[str, Any]],
    checkpoint_versions: tuple[int, ...],
) -> str:
    selection = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(",").join(sql.Identifier(row["name"]) for row in columns), sql.Identifier(*name.split("."))
    )
    arguments: tuple[Any, ...] = ()
    if name == "mingjing_core.schema_migrations":
        selection += sql.SQL(" WHERE version<=%s")
        arguments = (len(source.source.migrations),)
    elif name == "public.checkpoint_migrations":
        selection += sql.SQL(" WHERE v=ANY(%s)")
        arguments = (list(checkpoint_versions),)
    query = sql.SQL(
        "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) "
        "ORDER BY to_jsonb(t)::text COLLATE \"C\"),'[]'::jsonb)::text,'UTF8')),'hex') AS value FROM ({}) t"
    )
    return connection.execute(query.format(selection), arguments).fetchone()["value"]


def original_fields(
    connection: Any, source: BackupInputs, baseline: dict[str, Any], checkpoint_versions: tuple[int, ...]
) -> None:
    """Compare the M1 UTC/PG projection; new ledger rows do not hide changes to original rows."""
    try:
        _transaction(connection, source, "owner")
        _baseline(source, baseline, checkpoint_versions)
        connection.execute("SET LOCAL TimeZone='UTC'")
        for name, columns in baseline["columns"].items():
            _original_columns(connection, source, name, columns)
            require(
                _projected_hash(connection, source, name, columns, checkpoint_versions) == baseline["tables"][name],
                "SOURCE_POSTCHECK_ORIGINAL_FIELDS_CHANGED",
            )
    except psycopg.Error:
        raise RestoreRejected("SOURCE_POSTCHECK_QUERY_FAILED") from None


def _owned_objects(connection: Any, source: BackupInputs) -> list[dict[str, Any]]:
    schemas = connection.execute(
        "SELECT nspname,nspowner FROM pg_namespace WHERE nspname IN ('mingjing_core','public')"
    ).fetchall()
    require(
        len(schemas) == 2 and all(row["nspowner"] == source.source.owner_oid for row in schemas),
        "SOURCE_POSTCHECK_SCHEMA_OWNER",
    )
    rows = connection.execute(
        "SELECT c.oid,n.nspname||'.'||c.relname AS name,c.relkind::text AS kind,c.relowner "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S','v','m','f')"
    ).fetchall()
    require(rows and all(row["relowner"] == source.source.owner_oid for row in rows), "SOURCE_POSTCHECK_RELATION_OWNER")
    return rows


def _history(connection: Any, source: BackupInputs) -> None:
    rows = connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
    require(
        {str(row["version"]): row["checksum"] for row in rows} == dict(source.release.migrations),
        "SOURCE_POSTCHECK_HISTORY_1_8",
    )


def _checkpoint_history(connection: Any, checkpoint_versions: tuple[int, ...], saver_count: int | None) -> int:
    require(
        saver_count is None or type(saver_count) is int and saver_count >= len(checkpoint_versions),
        "SOURCE_POSTCHECK_SAVER_COUNT",
    )
    expected = checkpoint_versions if saver_count is None else tuple(range(saver_count))
    rows = connection.execute("SELECT v FROM public.checkpoint_migrations ORDER BY v").fetchall()
    require(tuple(row["v"] for row in rows) == expected, "SOURCE_POSTCHECK_CHECKPOINT_HISTORY")
    return len(expected)


def _empty(connection: Any, names: set[str]) -> None:
    for name in sorted(names):
        require(
            not connection.execute(
                sql.SQL("SELECT EXISTS(SELECT 1 FROM {}) AS occupied").format(sql.Identifier(*name.split(".")))
            ).fetchone()["occupied"],
            "SOURCE_POSTCHECK_NEW_OR_CENTRAL_TABLE_OCCUPIED",
        )


def _central_sequence(connection: Any) -> None:
    row = connection.execute(
        "SELECT last_value,log_cnt,is_called FROM mingjing_core.core_model_usage_id_seq"
    ).fetchone()
    require(row == {"last_value": 1, "log_cnt": 0, "is_called": False}, "SOURCE_POSTCHECK_CENTRAL_SEQUENCE_USED")


def _quiet(connection: Any, allowed_pids: set[int]) -> None:
    require(
        type(allowed_pids) is set
        and connection.info.backend_pid in allowed_pids
        and all(type(pid) is int and pid > 0 for pid in allowed_pids),
        "SOURCE_POSTCHECK_EXPLICIT_PIDS_REQUIRED",
    )
    sessions(connection, allowed_pids)
    busy = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM mingjing_core.core_runs "
        "WHERE status IN ('queued','running') OR lease_until>clock_timestamp()) AS busy"
    ).fetchone()["busy"]
    require(not busy, "SOURCE_POSTCHECK_ACTIVE_RUN_OR_LEASE")


def owner_state(
    connection: Any,
    source: BackupInputs,
    baseline: dict[str, Any],
    checkpoint_versions: tuple[int, ...],
    *,
    saver_count: int | None,
    allowed_pids: set[int],
) -> dict[str, Any]:
    try:
        identity = _transaction(connection, source, "owner")
        _quiet(connection, allowed_pids)
        verify_relations(connection)
        rows = _owned_objects(connection, source)
        routines(connection, source, 7)
        triggers(connection, 7)
        _history(connection, source)
        original_fields(connection, source, baseline, checkpoint_versions)
        checkpoints = _checkpoint_history(connection, checkpoint_versions, saver_count)
        owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
        require(owners == list(source.source.owners), "SOURCE_POSTCHECK_OWNER_SET")
        new_core = {"mingjing_core." + name for name in CORE_TABLES} - set(baseline["tables"])
        _empty(connection, new_core | set(QUOTA))
        _central_sequence(connection)
        _quiet(connection, allowed_pids)
    except psycopg.Error:
        raise RestoreRejected("SOURCE_POSTCHECK_QUERY_FAILED") from None
    return {
        "schema": "first-release-source-owner-postcheck-v1",
        "database_oid": identity["database_oid"],
        "owner_role_oid": identity["role_oid"],
        "relations_checked": len(rows),
        "original_fields_verified": True,
        "checkpoint_migrations_checked": checkpoints,
        "new_core_tables_checked": len(new_core),
        "central_ledger_empty": True,
        "central_sequence_unused": True,
        "source_write_authorized": False,
        "source_restore_content_verified": False,
        "runtime_verified": False,
        "global_quiescence_verified": False,
        "linux_attestation": False,
        "publication": False,
    }


def _writer_scope(connection: Any, source: BackupInputs) -> None:
    forbidden = connection.execute(
        "SELECT has_database_privilege(current_user,current_database(),'CREATE') OR "
        "has_database_privilege(current_user,current_database(),'TEMP') OR "
        "has_schema_privilege(current_user,'mingjing_core','CREATE') OR "
        "has_schema_privilege(current_user,'public','CREATE') OR pg_has_role(current_user,%s,'USAGE') AS bad",
        (source.source.owner_oid,),
    ).fetchone()["bad"]
    require(not forbidden, "SOURCE_POSTCHECK_WRITER_DDL_TEMP_OWNER")
    public = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_database d,"
        "LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a "
        "WHERE d.datname=current_database() AND a.grantee=0) OR "
        "EXISTS(SELECT 1 FROM pg_namespace n,"
        "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
        "WHERE n.nspname IN ('mingjing_core','public') AND a.grantee=0 AND a.privilege_type='CREATE') AS bad"
    ).fetchone()["bad"]
    require(not public, "SOURCE_POSTCHECK_PUBLIC_DATABASE_OR_SCHEMA_GRANT")
    require(
        connection.execute("SELECT has_database_privilege(current_user,current_database(),'CONNECT') AS ok").fetchone()[
            "ok"
        ],
        "SOURCE_POSTCHECK_WRITER_CONNECT",
    )
    for namespace in ("mingjing_core", "public"):
        require(
            connection.execute("SELECT has_schema_privilege(current_user,%s,'USAGE') AS ok", (namespace,)).fetchone()[
                "ok"
            ],
            "SOURCE_POSTCHECK_WRITER_SCHEMA_USAGE",
        )


def _sequence_acl(connection: Any, oid: int) -> None:
    for right in ("SELECT", "USAGE", "UPDATE"):
        row = connection.execute(
            "SELECT has_sequence_privilege(current_user,%s,%s) AS allowed,"
            "has_sequence_privilege(current_user,%s,%s) AS grantable",
            (oid, right, oid, right + " WITH GRANT OPTION"),
        ).fetchone()
        require(row["allowed"] == (right != "UPDATE") and not row["grantable"], "SOURCE_POSTCHECK_SEQUENCE_ACL")


def writer_state(connection: Any, source: BackupInputs, *, allowed_pids: set[int]) -> dict[str, Any]:
    try:
        identity = _transaction(connection, source, "writer")
        _quiet(connection, allowed_pids)
        verify_relations(connection)
        rows = _owned_objects(connection, source)
        routines(connection, source, 7)
        triggers(connection, 7)
        _history(connection, source)
        _writer_scope(connection, source)
        for row in rows:
            if row["kind"] == "S":
                require(row["name"] == USAGE_SEQUENCE, "SOURCE_POSTCHECK_UNEXPECTED_SEQUENCE")
                _sequence_acl(connection, row["oid"])
            else:
                rights = frozenset({"SELECT"}) if row["name"] in LEDGERS else QUOTA.get(row["name"], DML)
                table_acl(connection, row["oid"], rights)
        _quiet(connection, allowed_pids)
    except psycopg.Error:
        raise RestoreRejected("SOURCE_POSTCHECK_QUERY_FAILED") from None
    return {
        "schema": "first-release-source-writer-postcheck-v1",
        "database_oid": identity["database_oid"],
        "writer_role_oid": identity["role_oid"],
        "tables_checked": sum(row["kind"] == "r" for row in rows),
        "sequences_checked": sum(row["kind"] == "S" for row in rows),
        "quota_tables_checked": len(QUOTA),
        "source_write_authorized": False,
        "global_quiescence_verified": False,
        "runtime_verified": False,
        "linux_attestation": False,
        "publication": False,
    }

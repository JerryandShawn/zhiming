"""Read actual restore identities/state and probe DML-only writer permissions."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from tools.b1_restore_proof_contracts import ProofRequest
from tools.b1_restore_replay_contracts import require
from tools.core_incremental_contracts import MIGRATIONS, digest


def connection(request: ProofRequest, role: str) -> Any:
    return psycopg.connect(request.dsns()[role], row_factory=dict_row, connect_timeout=5)


def identity(conn: Any, request: ProofRequest, role: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT current_database() AS database,current_user AS role,host(inet_server_addr()) AS host,"
        "inet_server_port() AS port,current_setting('server_version_num')::int AS version_num,version() AS build"
    ).fetchone()
    require(row["database"] == request.database and row["role"] == request.database + "_" + role, "RESTORE_IDENTITY")
    require(row["host"] in {"127.0.0.1", "::1"}, "SERVER_LOOPBACK_ONLY")
    require(row["port"] in ({55480, 55481} if request.local_drill else {5432}), "RESTORE_PORT")
    require(150000 <= row["version_num"] < 160000, "POSTGRES15_REQUIRED")
    require(request.local_drill or "linux" in row["build"].lower(), "LINUX_POSTGRES_REQUIRED")
    elevated = conn.execute(
        "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR "
        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)) "
        "AS elevated FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    require(elevated is not None and not elevated["elevated"], "RESTORE_ROLE_ELEVATED")
    owner = conn.execute(
        "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    require(owner["owner"] == request.database + "_owner", "DATABASE_OWNER")
    return {key: row[key] for key in ("database", "role", "host", "port", "version_num")}


def quiescent(conn: Any) -> None:
    count = conn.execute(
        "SELECT count(*) AS count FROM pg_stat_activity WHERE datname=current_database() "
        "AND pid<>pg_backend_pid() AND backend_type='client backend'"
    ).fetchone()["count"]
    require(count == 0, "OTHER_RESTORE_SESSIONS")


def empty_target(request: ProofRequest) -> dict[str, Any]:
    with connection(request, "owner") as conn:
        observed = identity(conn, request, "owner")
        quiescent(conn)
        counts = conn.execute(
            "SELECT (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%%') + "
            "(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname NOT IN ('pg_catalog','information_schema')) AS objects,"
            "(SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
            "('pg_catalog','information_schema','public','pg_toast')) AS namespaces,"
            "(SELECT count(*) FROM pg_type WHERE typnamespace='public'::regnamespace) AS types,"
            "(SELECT count(*) FROM pg_extension WHERE extname<>'plpgsql') AS extensions"
        ).fetchone()
        require(all(value == 0 for value in counts.values()), "RESTORE_TARGET_NOT_EMPTY")
    with connection(request, "writer") as conn:
        identity(conn, request, "writer")
    return observed


def checksums(conn: Any) -> dict[str, str]:
    return {
        str(row["version"]): row["checksum"]
        for row in conn.execute("SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version")
    }


def state_hash(conn: Any) -> str:
    # Matches PostgresPort._state, so the restored schema4 is bound to B2's exact dump state.
    tables = conn.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname='mingjing_core' OR "
        "schemaname='public' AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes',"
        "'checkpoint_migrations') ORDER BY schemaname,tablename"
    ).fetchall()
    hashes = {}
    for row in tables:
        query = sql.SQL(
            "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),"
            "'[]'::jsonb)::text,'UTF8')),'hex') AS hash FROM {}.{} t"
        ).format(sql.Identifier(row["schemaname"]), sql.Identifier(row["tablename"]))
        hashes[row["schemaname"] + "." + row["tablename"]] = conn.execute(query).fetchone()["hash"]
    return digest(hashes)


def restored_snapshot(request: ProofRequest, expected_state: str) -> dict[str, Any]:
    with connection(request, "owner") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='30s'")
        identity(conn, request, "owner")
        quiescent(conn)
        ledger = checksums(conn)
        require(ledger == {str(key): MIGRATIONS[str(key)] for key in range(1, 5)}, "RESTORED_SCHEMA4_REQUIRED")
        actual = state_hash(conn)
        require(actual == expected_state, "RESTORE_CONTENT_MISMATCH")
        runs = conn.execute(
            "SELECT count(*) FILTER(WHERE status IN ('queued','running')) AS active,"
            "count(*) FILTER(WHERE lease_until>now()) AS leases FROM mingjing_core.core_runs"
        ).fetchone()
        require(runs == {"active": 0, "leases": 0}, "RESTORE_NOT_QUIESCENT")
        return {"state_sha256": actual, "checksums": ledger}


class _ProbeSucceeded(Exception):
    """Rollback a successful forbidden probe without leaving an object or row."""


def denied(conn: Any, query: str) -> bool:
    try:
        with conn.transaction():
            conn.execute(query)
            raise _ProbeSucceeded
    except psycopg.errors.InsufficientPrivilege:
        return True
    except _ProbeSucceeded:
        return False


def writer_permissions(request: ProofRequest) -> dict[str, Any]:
    with connection(request, "writer") as conn:
        observed = identity(conn, request, "writer")
        elevated = conn.execute(
            "SELECT has_database_privilege(current_user,current_database(),'CREATE') OR "
            "has_database_privilege(current_user,current_database(),'TEMP') OR "
            "has_schema_privilege(current_user,'mingjing_core','CREATE') OR "
            "has_schema_privilege(current_user,'public','CREATE') OR EXISTS(SELECT 1 FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public') "
            "AND pg_has_role(current_user,c.relowner,'USAGE')) OR EXISTS(SELECT 1 FROM pg_tables t "
            "WHERE t.schemaname IN ('mingjing_core','public') AND has_table_privilege(current_user,"
            "quote_ident(t.schemaname)||'.'||quote_ident(t.tablename),'TRUNCATE,REFERENCES,TRIGGER')) AS elevated"
        ).fetchone()["elevated"]
        require(not elevated, "WRITER_OWNERSHIP_OR_DDL")
        tables = conn.execute(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname='mingjing_core' OR "
            "schemaname='public' AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes',"
            "'checkpoint_migrations')"
        ).fetchall()
        ledgers = {"mingjing_core.schema_migrations", "public.checkpoint_migrations"}
        require(ledgers <= {row["schemaname"] + "." + row["tablename"] for row in tables}, "CHECKPOINT_LEDGER_MISSING")
        for row in tables:
            table = row["schemaname"] + "." + row["tablename"]
            required = ["SELECT"] if table in ledgers else ["SELECT", "INSERT", "UPDATE", "DELETE"]
            for right in required:
                require(
                    conn.execute("SELECT has_table_privilege(current_user,%s,%s) AS ok", (table, right)).fetchone()[
                        "ok"
                    ],
                    "WRITER_GRANT_MISSING",
                )
            if table in ledgers:
                require(
                    not conn.execute(
                        "SELECT has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') AS ok",
                        (table,),
                    ).fetchone()["ok"],
                    "WRITER_LEDGER_WRITABLE",
                )
        probes = [
            "CREATE TABLE mingjing_core.b1_forbidden_probe(id int)",
            "CREATE TABLE public.b1_forbidden_probe(id int)",
            "CREATE TEMP TABLE b1_forbidden_probe(id int)",
            "INSERT INTO mingjing_core.schema_migrations(version) SELECT 999 WHERE false",
            "INSERT INTO public.checkpoint_migrations(v) SELECT 999 WHERE false",
        ]
        require(all(denied(conn, query) for query in probes), "WRITER_FORBIDDEN_PROBE_SUCCEEDED")
    return {"identity": observed, "tables_checked": len(tables), "forbidden_probes_denied": len(probes)}

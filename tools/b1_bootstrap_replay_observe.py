"""Read-only identity, complete schema4 fixture observations, and canonical hashes."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from tools.b1_bootstrap_replay_fixture import SCHEMA4, SeedRequest, require
from tools.b1_restore_proof_pg import checksums, state_hash

CORE_TABLES = frozenset(
    {
        "schema_migrations",
        "core_owners",
        "core_subjects",
        "core_versions",
        "core_entities",
        "core_operations",
        "core_channels",
        "core_revocations",
        "core_legacy_map",
        "core_runs",
        "core_model_charges",
        "tarot_draws",
        "tarot_requests",
        "tarot_readings",
        "delivery_outbox",
        "core_mutation_requests",
        "core_media_deletions",
    }
)
CHECKPOINT_TABLES = frozenset({"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"})


def identity(conn: Any, request: SeedRequest) -> dict[str, Any]:
    fields = conninfo_to_dict(request.dsn())
    row = conn.execute(
        "SELECT current_database() AS database,current_user AS role,host(inet_server_addr()) AS host,"
        "inet_server_port() AS port,current_setting('server_version_num')::int AS version"
    ).fetchone()
    require(
        row["database"] == fields["dbname"]
        and row["role"] == fields["user"]
        and row["host"] == fields["host"]
        and row["port"] == int(fields["port"]),
        "SEED_IDENTITY",
    )
    require(150000 <= row["version"] < 160000, "SEED_POSTGRES15")
    roles = conn.execute(
        "SELECT rolname,rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR "
        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) AS elevated "
        "FROM pg_roles WHERE rolname=ANY(%s)",
        ([fields["dbname"] + "_" + role for role in ("owner", "writer")],),
    ).fetchall()
    require(len(roles) == 2 and all(not role["elevated"] for role in roles), "SEED_ROLES")
    owner = conn.execute(
        "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
    ).fetchone()["owner"]
    require(owner == fields["user"], "SEED_DATABASE_OWNER")
    count = conn.execute(
        "SELECT count(*) AS n FROM pg_stat_activity WHERE datname=current_database() "
        "AND pid<>pg_backend_pid() AND backend_type='client backend'"
    ).fetchone()["n"]
    require(count == 0, "SEED_OTHER_SESSIONS")
    require(checksums(conn) == SCHEMA4, "SEED_SCHEMA4_REQUIRED")
    busy = conn.execute(
        "SELECT count(*) AS n FROM mingjing_core.core_runs WHERE status IN ('queued','running') OR lease_until>now()"
    ).fetchone()["n"]
    require(busy == 0, "SEED_ACTIVE_RUN")
    return row


def table_sets(conn: Any, checkpoint: bool) -> None:
    rows = conn.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname NOT IN "
        "('pg_catalog','information_schema') AND schemaname NOT LIKE 'pg_toast%%'"
    ).fetchall()
    expected = {("mingjing_core", table) for table in CORE_TABLES}
    if checkpoint:
        expected |= {("public", table) for table in CHECKPOINT_TABLES}
    require({(row["schemaname"], row["tablename"]) for row in rows} == expected, "SEED_TABLE_SET")
    owners = conn.execute(
        "SELECT count(*) AS n FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S') "
        "AND pg_get_userbyid(c.relowner)<>current_user"
    ).fetchone()["n"]
    require(owners == 0, "SEED_TABLE_OWNER")
    extra = conn.execute(
        "SELECT (SELECT count(*) FROM pg_namespace WHERE nspname NOT IN "
        "('pg_catalog','information_schema','pg_toast','public','mingjing_core')) + "
        "(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('public','mingjing_core') AND c.relkind NOT IN ('r','i','S')) + "
        "(SELECT count(*) FROM pg_extension WHERE extname<>'plpgsql') AS n"
    ).fetchone()["n"]
    require(extra == 0, "SEED_EXTRA_SCHEMA_OBJECT")


def snapshot(conn: Any) -> dict[str, Any]:
    rows = {}
    for table in CORE_TABLES - {"schema_migrations"}:
        query = sql.SQL("SELECT * FROM mingjing_core.{} ORDER BY to_jsonb({})::text").format(
            sql.Identifier(table), sql.Identifier(table)
        )
        rows[table] = conn.execute(query).fetchall()
    mapping = {
        "owners": "core_owners",
        "subjects": "core_subjects",
        "entities": "core_entities",
        "runs": "core_runs",
        "outbox": "delivery_outbox",
    }
    result = {name: rows.pop(table) for name, table in mapping.items()}
    result["subjects"] = sorted(result["subjects"], key=lambda row: (row["owner"], row["id"]))
    return dict(result, other=rows)


def checkpoint_counts(conn: Any) -> dict[str, int]:
    return {
        table: conn.execute(sql.SQL("SELECT count(*) AS n FROM public.{}").format(sql.Identifier(table))).fetchone()[
            "n"
        ]
        for table in sorted(CHECKPOINT_TABLES)
    }


def observe(request: SeedRequest, *, checkpoint: bool) -> dict[str, Any]:
    with psycopg.connect(request.dsn(), row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        conn.execute("SET LOCAL statement_timeout='30s'")
        observed = identity(conn, request)
        table_sets(conn, checkpoint)
        return {
            "identity": observed,
            "snapshot": snapshot(conn),
            "state_sha256": state_hash(conn),
            "checkpoints": checkpoint_counts(conn) if checkpoint else {},
        }

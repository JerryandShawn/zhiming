"""Read-only PostgreSQL15 exact ACL checks; never repair a role to satisfy a proof."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row

from tools.first_release_contracts import ReleasePin, RestoreContract, RestoreRejected, require

TABLE_RIGHTS = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
DML = frozenset(TABLE_RIGHTS[:4])
LEDGERS = {"mingjing_core.schema_migrations", "public.checkpoint_migrations"}
CHECKPOINTS = {"public.checkpoints", "public.checkpoint_blobs", "public.checkpoint_writes"}
QUOTA = {
    "mingjing_core.core_model_accounts": frozenset({"SELECT", "UPDATE"}),
    "mingjing_core.core_model_usage": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "mingjing_core.core_model_batches": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "mingjing_core.core_model_authorizations": frozenset({"SELECT", "INSERT"}),
}
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
        "core_run_steps",
        "core_run_events",
        "core_embeddings",
        "core_model_accounts",
        "core_model_batches",
        "core_model_authorizations",
        "core_model_usage",
    }
)
RETIREMENT_BODY_SHA = "43309838f66fdd60edd9d3892c17c6f292d8080e112b1c87c55f1399aef95a86"


def verify_relations(connection: Any) -> None:
    # Views/rules and foreign relations can expose owner privileges despite correct base-table grants.
    expected = {(name, "r") for name in ("mingjing_core." + table for table in CORE_TABLES)}
    expected |= {(name, "r") for name in LEDGERS | CHECKPOINTS if name.startswith("public.")}
    expected.add(("mingjing_core.core_model_usage_id_seq", "S"))
    actual = connection.execute(
        "SELECT n.nspname||'.'||c.relname AS name,c.relkind::text AS kind "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S','v','m','f')"
    ).fetchall()
    require({(row["name"], row["kind"]) for row in actual} == expected, "UNREVIEWED_RELATION_SURFACE")
    rules = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class "
        "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public')) AS bad"
    ).fetchone()["bad"]
    require(not rules, "UNREVIEWED_RELATION_RULE")


def verify_routines(connection: Any, contract: RestoreContract) -> None:
    elevated = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND has_schema_privilege(current_user,n.oid,'USAGE') "
        "AND has_function_privilege(current_user,p.oid,'EXECUTE')) AS bad"
    ).fetchone()["bad"]
    require(not elevated, "EXECUTABLE_SECURITY_DEFINER_ROUTINE")
    rows = connection.execute(
        "SELECT n.nspname||'.'||p.proname AS name,pg_get_userbyid(p.proowner) AS owner,"
        "p.prokind,p.pronargs,p.prosecdef,p.proleakproof,p.proisstrict,p.provolatile,p.proparallel,p.proconfig,"
        "p.prorettype::regtype::text AS result,l.lanname,"
        "encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS body_sha "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang "
        "WHERE n.nspname IN ('mingjing_core','public')"
    ).fetchall()
    require(len(rows) == 1, "UNREVIEWED_ROUTINE_SURFACE")
    row = rows[0]
    expected = dict(
        name="mingjing_core.clear_retired_embeddings",
        owner=contract.database + "_owner",
        prokind="f",
        pronargs=0,
        prosecdef=False,
        proleakproof=False,
        proisstrict=False,
        provolatile="v",
        proparallel="u",
        proconfig=["search_path=mingjing_core"],
        result="trigger",
        lanname="plpgsql",
        body_sha=RETIREMENT_BODY_SHA,
    )
    require(row == expected, "REVIEWED_RETIREMENT_TRIGGER_CHANGED")


def identity(connection: Any, contract: RestoreContract, role: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version_num,version() AS build,"
        "current_setting('transaction_read_only') AS read_only,current_setting('search_path') AS search_path,"
        "current_schemas(false)::text[] AS schemas"
    ).fetchone()
    require(row["search_path"] == "pg_catalog" and row["schemas"] == ["pg_catalog"], "TRUSTED_CATALOG_PATH_REQUIRED")
    require(
        row["database"] == contract.database
        and row["role"] == contract.database + "_" + role
        and row["session_role"] == row["role"],
        "ACTUAL_DATABASE_ROLE_MISMATCH",
    )
    require(row["host"] in {"127.0.0.1", "::1"}, "ACTUAL_SERVER_NOT_LOOPBACK")
    require(row["port"] in ({55480, 55481} if contract.local_drill else {5432}), "ACTUAL_SERVER_PORT")
    require(150000 <= row["version_num"] < 160000, "POSTGRES15_REQUIRED")
    require(contract.local_drill or "linux" in row["build"].lower(), "LINUX_POSTGRES_REQUIRED")
    require(row["read_only"] == "on", "READ_ONLY_ACL_TRANSACTION_REQUIRED")
    unsafe = connection.execute(
        "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR "
        "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) AS unsafe "
        "FROM pg_roles WHERE rolname=current_user"
    ).fetchone()
    require(unsafe is not None and not unsafe["unsafe"], "ELEVATED_OR_INHERITED_ROLE")
    owner = connection.execute(
        "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    require(owner["owner"] == contract.database + "_owner", "ACTUAL_DATABASE_OWNER")
    return {key: row[key] for key in ("database", "role", "host", "port", "version_num")}


def verify_ownership(connection: Any, contract: RestoreContract) -> None:
    forbidden = connection.execute(
        "SELECT has_database_privilege(current_user,current_database(),'CREATE') OR "
        "has_database_privilege(current_user,current_database(),'TEMP') OR "
        "has_schema_privilege(current_user,'mingjing_core','CREATE') OR "
        "has_schema_privilege(current_user,'public','CREATE') OR "
        "EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND pg_has_role(current_user,c.relowner,'USAGE')) OR "
        "EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND pg_has_role(current_user,p.proowner,'USAGE')) OR "
        "EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname IN ('mingjing_core','public') "
        "AND pg_has_role(current_user,n.nspowner,'USAGE')) AS bad"
    ).fetchone()["bad"]
    require(not forbidden, "WRITER_DDL_TEMP_OR_OWNERSHIP")
    for schema in ("mingjing_core", "public"):
        require(
            connection.execute("SELECT has_schema_privilege(current_user,%s,'USAGE') AS ok", (schema,)).fetchone()[
                "ok"
            ],
            "WRITER_SCHEMA_USAGE_MISSING",
        )
    require(
        connection.execute("SELECT has_database_privilege(current_user,current_database(),'CONNECT') AS ok").fetchone()[
            "ok"
        ],
        "WRITER_CONNECT_MISSING",
    )
    objects = connection.execute(
        "SELECT pg_get_userbyid(c.relowner) AS owner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S','v','m','f')"
    ).fetchall()
    require(objects and all(row["owner"] == contract.database + "_owner" for row in objects), "RESTORED_OBJECT_OWNER")
    public = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_database d,"
        "LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a "
        "WHERE d.datname=current_database() AND a.grantee=0) OR "
        "EXISTS(SELECT 1 FROM pg_namespace n,"
        "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
        "WHERE n.nspname IN ('mingjing_core','public') AND a.grantee=0 AND a.privilege_type='CREATE') AS bad"
    ).fetchone()["bad"]
    require(not public, "PUBLIC_DATABASE_OR_SCHEMA_GRANT")


def table_acl(connection: Any, oid: int, expected: frozenset[str]) -> None:
    for right in TABLE_RIGHTS:
        row = connection.execute(
            "SELECT has_table_privilege(current_user,%s,%s) AS allowed,"
            "has_table_privilege(current_user,%s,%s) AS grantable",
            (oid, right, oid, right + " WITH GRANT OPTION"),
        ).fetchone()
        require(row["allowed"] == (right in expected) and not row["grantable"], "EXACT_TABLE_ACL_MISMATCH")
    for right in ("SELECT", "INSERT", "UPDATE", "REFERENCES"):
        row = connection.execute(
            "SELECT has_any_column_privilege(current_user,%s,%s) AS allowed,"
            "has_any_column_privilege(current_user,%s,%s) AS grantable",
            (oid, right, oid, right + " WITH GRANT OPTION"),
        ).fetchone()
        require(row["allowed"] == (right in expected) and not row["grantable"], "EXACT_COLUMN_ACL_MISMATCH")


def verify_writer(connection: Any, contract: RestoreContract, pin: ReleasePin) -> dict[str, int]:
    verify_relations(connection)
    verify_routines(connection, contract)
    verify_ownership(connection, contract)
    tables = connection.execute(
        "SELECT c.oid,n.nspname||'.'||c.relname AS name FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='mingjing_core' AND c.relkind IN ('r','p','v','m','f') OR "
        "n.nspname='public' AND c.relname IN ('checkpoints','checkpoint_blobs','checkpoint_writes',"
        "'checkpoint_migrations') AND c.relkind IN ('r','p')"
    ).fetchall()
    require(LEDGERS | CHECKPOINTS | set(QUOTA) <= {row["name"] for row in tables}, "REQUIRED_ACL_TABLE_MISSING")
    for row in tables:
        expected = frozenset({"SELECT"}) if row["name"] in LEDGERS else QUOTA.get(row["name"], DML)
        table_acl(connection, row["oid"], expected)
    sequences = connection.execute(
        "SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind='S'"
    ).fetchall()
    for row in sequences:
        for right in ("SELECT", "USAGE", "UPDATE"):
            actual = connection.execute(
                "SELECT has_sequence_privilege(current_user,%s,%s) AS ok,"
                "has_sequence_privilege(current_user,%s,%s) AS grantable",
                (row["oid"], right, row["oid"], right + " WITH GRANT OPTION"),
            ).fetchone()
            require(actual["ok"] == (right != "UPDATE") and not actual["grantable"], "EXACT_SEQUENCE_ACL_MISMATCH")
    migrations = connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
    require(
        {str(row["version"]): row["checksum"] for row in migrations} == dict(pin.migrations),
        "ACTUAL_MIGRATIONS_1_8_MISMATCH",
    )
    return {"tables_checked": len(tables), "sequences_checked": len(sequences), "quota_tables_checked": len(QUOTA)}


def verify_database_acl(
    contract: RestoreContract, pin: ReleasePin, *, environment: Mapping[str, str] | None = None
) -> dict[str, Any]:
    dsns = contract.dsns(environment)
    observed: dict[str, Any] = {}
    try:
        for role in ("owner", "writer"):
            with (
                psycopg.connect(dsns[role], autocommit=True, row_factory=dict_row, connect_timeout=5) as connection,
                connection.transaction(),
            ):
                connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                # Role/database defaults may contain owner views that hide real catalogs from unqualified queries.
                connection.execute("SET LOCAL search_path=pg_catalog")
                observed[role] = identity(connection, contract, role)
                if role == "writer":
                    observed.update(verify_writer(connection, contract, pin))
    except psycopg.Error:
        raise RestoreRejected("LOCAL_ACL_QUERY_FAILED") from None
    return {
        **observed,
        "database_connections": 2,
        "read_only": True,
        "mutations": 0,
        "native_restore_completed": False,
        "publication": False,
        "linux_attestation": False,
    }

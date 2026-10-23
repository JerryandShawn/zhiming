"""Exact existing Core4/7 relations, writer ACLs and the real retirement-trigger attachment."""

from __future__ import annotations

from typing import Any

from tools.first_release_acl import CORE_TABLES, DML, RETIREMENT_BODY_SHA, table_acl
from tools.first_release_contracts import require
from tools.first_release_incremental import BackupInputs

CHECKPOINTS = frozenset({"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"})
QUOTA = frozenset({"core_model_accounts", "core_model_usage", "core_model_authorizations", "core_model_batches"})
LATE_TABLES = frozenset({"core_run_steps", "core_run_events", "core_embeddings"})


def expected_relations(prefix: int) -> set[str]:
    require(type(prefix) is int and prefix in {4, 7}, "SOURCE_PROFILE_PREFIX_4_7_ONLY")
    names = CORE_TABLES - QUOTA - (LATE_TABLES if prefix == 4 else set())
    return {"mingjing_core." + name for name in names} | {"public." + name for name in CHECKPOINTS}


def checked_identity(connection: Any, inputs: BackupInputs, role: str) -> dict[str, Any]:
    require(role in {"owner", "writer"}, "SOURCE_PROFILE_ROLE")
    row = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version,current_setting('search_path') AS path,"
        "current_schemas(false)::text[] AS schemas,"
        "(SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,"
        "r.oid AS role_oid,r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls "
        "OR r.rolinherit OR NOT r.rolcanlogin OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS unsafe "
        "FROM pg_roles r WHERE r.rolname=current_user"
    ).fetchone()
    require(
        row
        and row["database"] == inputs.source.database
        and row["role"] == row["session_role"] == inputs.source.database + "_" + role
        and row["role_oid"] == getattr(inputs.source, role + "_oid")
        and row["database_oid"] == inputs.source.database_oid,
        "SOURCE_PROFILE_ACTUAL_IDENTITY",
    )
    require(
        (row["host"], row["port"]) == (connection.info.host, connection.info.port)
        and row["port"] in {55480, 55481}
        and 150000 <= row["version"] < 160000
        and row["path"] == "pg_catalog"
        and row["schemas"] == ["pg_catalog"]
        and not row["unsafe"],
        "SOURCE_PROFILE_LOCATION_OR_ROLE",
    )
    require(
        connection.execute(
            "SELECT datdba=%s AS owned FROM pg_database WHERE datname=current_database()", (inputs.source.owner_oid,)
        ).fetchone()["owned"],
        "SOURCE_PROFILE_DATABASE_OWNER",
    )
    return row


def routines(connection: Any, inputs: BackupInputs, prefix: int) -> None:
    require(
        not connection.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema') "
            "AND has_schema_privilege(current_user,n.oid,'USAGE') "
            "AND has_function_privilege(current_user,p.oid,'EXECUTE')) AS bad"
        ).fetchone()["bad"],
        "SOURCE_PROFILE_EXECUTABLE_DEFINER",
    )
    rows = connection.execute(
        "SELECT n.nspname||'.'||p.proname AS name,pg_get_userbyid(p.proowner) AS owner,"
        "p.prokind,p.pronargs,p.prosecdef,p.proleakproof,p.proisstrict,p.provolatile,p.proparallel,p.proconfig,"
        "p.prorettype::regtype::text AS result,l.lanname,"
        "encode(sha256(convert_to(p.prosrc,'UTF8')),'hex') AS body_sha "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace JOIN pg_language l ON l.oid=p.prolang "
        "WHERE n.nspname IN ('mingjing_core','public')"
    ).fetchall()
    if prefix == 4:
        require(not rows, "SOURCE_PROFILE4_ROUTINE_REJECTED")
        return
    expected = dict(
        name="mingjing_core.clear_retired_embeddings",
        owner=inputs.source.database + "_owner",
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
    require(rows == [expected], "SOURCE_PROFILE7_RETIREMENT_FUNCTION")


def triggers(connection: Any, prefix: int) -> None:
    rows = connection.execute(
        "SELECT t.tgname,n.nspname||'.'||c.relname AS relation,t.tgtype::int AS type,"
        "t.tgenabled::text AS enabled,pn.nspname||'.'||p.proname AS routine,t.tgnargs AS nargs,"
        "encode(t.tgargs,'hex') AS arguments,t.tgqual IS NULL AS unconditional,"
        "t.tgconstraint=0 AS nonconstraint,t.tgdeferrable,t.tginitdeferred,t.tgoldtable,t.tgnewtable,"
        "ARRAY(SELECT a.attname::text FROM unnest(t.tgattr::smallint[]) WITH ORDINALITY x(num,pos) "
        "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=x.num AND NOT a.attisdropped ORDER BY x.pos) AS columns "
        "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_proc p ON p.oid=t.tgfoid JOIN pg_namespace pn ON pn.oid=p.pronamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND NOT t.tgisinternal"
    ).fetchall()
    if prefix == 4:
        require(not rows, "SOURCE_PROFILE4_TRIGGER_REJECTED")
        return
    require(len(rows) == 1, "SOURCE_PROFILE7_TRIGGER_COUNT")
    row = dict(rows[0])
    columns = row.pop("columns")
    expected = dict(
        tgname="core_embedding_retirement",
        relation="mingjing_core.core_entities",
        type=17,
        enabled="O",
        routine="mingjing_core.clear_retired_embeddings",
        nargs=0,
        arguments="",
        unconditional=True,
        nonconstraint=True,
        tgdeferrable=False,
        tginitdeferred=False,
        tgoldtable=None,
        tgnewtable=None,
    )
    require(row == expected and len(columns) == 2 and set(columns) == {"status", "data"}, "SOURCE_PROFILE7_TRIGGER")


def writer_privileges(connection: Any, inputs: BackupInputs, objects: list[dict[str, Any]]) -> None:
    forbidden = connection.execute(
        "SELECT has_database_privilege(current_user,current_database(),'CREATE') OR "
        "has_database_privilege(current_user,current_database(),'TEMP') OR "
        "has_schema_privilege(current_user,'mingjing_core','CREATE') OR "
        "has_schema_privilege(current_user,'public','CREATE') OR "
        "pg_has_role(current_user,%s,'USAGE') AS bad",
        (inputs.source.owner_oid,),
    ).fetchone()["bad"]
    require(not forbidden, "SOURCE_PROFILE_WRITER_DDL_TEMP_OWNER")
    public = connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_database d,"
        "LATERAL aclexplode(coalesce(d.datacl,acldefault('d',d.datdba))) a "
        "WHERE d.datname=current_database() AND a.grantee=0) OR "
        "EXISTS(SELECT 1 FROM pg_namespace n,"
        "LATERAL aclexplode(coalesce(n.nspacl,acldefault('n',n.nspowner))) a "
        "WHERE n.nspname IN ('mingjing_core','public') AND a.grantee=0 AND a.privilege_type='CREATE') AS bad"
    ).fetchone()["bad"]
    require(not public, "SOURCE_PROFILE_PUBLIC_DATABASE_OR_SCHEMA_GRANT")
    require(
        connection.execute("SELECT has_database_privilege(current_user,current_database(),'CONNECT') AS ok").fetchone()[
            "ok"
        ],
        "SOURCE_PROFILE_WRITER_CONNECT_MISSING",
    )
    for namespace in ("mingjing_core", "public"):
        require(
            connection.execute("SELECT has_schema_privilege(current_user,%s,'USAGE') AS ok", (namespace,)).fetchone()[
                "ok"
            ],
            "SOURCE_PROFILE_WRITER_SCHEMA_USAGE",
        )
    for row in objects:
        rights = (
            frozenset({"SELECT"})
            if row["name"].endswith(".schema_migrations") or row["name"] == "public.checkpoint_migrations"
            else DML
        )
        table_acl(connection, row["oid"], rights)


def verify_source_profile(connection: Any, inputs: BackupInputs, role: str) -> dict[str, Any]:
    prefix = len(inputs.source.migrations)
    expected = expected_relations(prefix)
    checked_identity(connection, inputs, role)
    history = connection.execute("SELECT version,checksum FROM mingjing_core.schema_migrations").fetchall()
    require(
        {str(row["version"]): row["checksum"] for row in history} == dict(inputs.source.migrations),
        "SOURCE_PROFILE_EXACT_HISTORY",
    )
    schemas = connection.execute(
        "SELECT nspname,nspowner FROM pg_namespace WHERE nspname IN ('mingjing_core','public')"
    ).fetchall()
    require(
        len(schemas) == 2 and all(row["nspowner"] == inputs.source.owner_oid for row in schemas),
        "SOURCE_PROFILE_SCHEMAS",
    )
    objects = connection.execute(
        "SELECT c.oid,n.nspname||'.'||c.relname AS name,c.relkind::text AS kind,c.relowner "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname IN ('mingjing_core','public') AND c.relkind IN ('r','p','S','v','m','f')"
    ).fetchall()
    require(
        {row["name"] for row in objects} == expected
        and all(row["kind"] == "r" and row["relowner"] == inputs.source.owner_oid for row in objects),
        "SOURCE_PROFILE_RELATIONS_OR_SEQUENCE",
    )
    require(
        not connection.execute(
            "SELECT EXISTS(SELECT 1 FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public')) AS bad"
        ).fetchone()["bad"],
        "SOURCE_PROFILE_RULE_REJECTED",
    )
    routines(connection, inputs, prefix)
    triggers(connection, prefix)
    if role == "writer":
        writer_privileges(connection, inputs, objects)
    return {"prefix": prefix, "relations_checked": len(objects), "retirement_trigger_checked": prefix == 7}

"""Injectable PostgreSQL/command boundary; candidate business code runs from its pinned release."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from psycopg import Error as PsycopgError
from psycopg import connect, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.core_incremental_contracts import Request, UpgradeRejected, digest, require
from tools.core_incremental_files import regular

IMPLICIT_PG_ENV = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGUSER",
    "PGSERVICE",
    "PGSERVICEFILE",
    "PGSYSCONFDIR",
    "PGOPTIONS",
    "PGPASSFILE",
    "PGPASSWORD",
)
DSN_FIELDS = {"host", "hostaddr", "port", "dbname", "user", "password", "passfile", "options", "connect_timeout"}


def _reject_implicit_pg() -> None:
    require(not any(os.environ.get(key) for key in IMPLICIT_PG_ENV), "IMPLICIT_PG_ENVIRONMENT")


def _controlled_dsn(request: Request, role: str, value: str) -> str:
    try:
        fields = conninfo_to_dict(value) if value else {}
    except (PsycopgError, ValueError):
        raise UpgradeRejected("PG_DSN_INVALID") from None
    require(set(fields) <= DSN_FIELDS, "PG_DSN_FIELDS")
    host = fields.get("host", "")
    require(host in {"127.0.0.1", "::1"} and fields.get("hostaddr", host) == host, "LOOPBACK_ONLY")
    require(fields.get("port", "5432") == "5432" and fields.get("dbname") == request.database, "DATABASE_IDENTITY")
    require(fields.get("user") == request.database + "_" + role, "SEPARATE_DATABASE_ROLES")
    require(fields.get("options", "") == "" and fields.get("connect_timeout", "5") == "5", "PG_DSN_OPTIONS")
    passfile = fields.get("passfile", os.path.abspath(os.devnull))
    if passfile not in {os.devnull, os.path.abspath(os.devnull)}:
        require(Path(passfile).is_absolute(), "PASSFILE_ABSOLUTE")
        regular(Path(passfile), private=True)
    fields.update(hostaddr=host, port="5432", options="", connect_timeout="5", passfile=os.path.abspath(passfile))
    return make_conninfo(**fields)


def _controlled_dsns(request: Request, values: dict[str, str]) -> dict[str, str]:
    _reject_implicit_pg()
    result = {role: _controlled_dsn(request, role, value) for role, value in values.items()}
    identities = {
        tuple(conninfo_to_dict(value)[key] for key in ("hostaddr", "port", "dbname")) for value in result.values()
    }
    require(len(identities) == 1, "PG_SERVER_MISMATCH")
    return result


class CommandRunner(Protocol):
    def run(
        self,
        args: list[str],
        *,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
        output: Path | None = None,
    ) -> bytes: ...


class PostgresPort:
    def __init__(
        self,
        request: Request,
        runner: CommandRunner,
        *,
        connector: Callable[..., Any] | None = None,
    ) -> None:
        self.request, self.runner, self.connector = (
            request,
            runner,
            connector or connect,
        )
        self.dsns = _controlled_dsns(
            request, {role: os.environ.get(f"CORE_INCREMENTAL_{role.upper()}_DSN", "") for role in ("owner", "writer")}
        )

    def _connection(self, role: str) -> Any:
        self.dsns = _controlled_dsns(self.request, self.dsns)
        return self.connector(self.dsns[role], row_factory=dict_row, connect_timeout=5)

    def _identity(self, connection: Any, role: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT current_database() AS database,current_user AS role,host(inet_server_addr()) AS host,"
            "inet_server_port() AS port,current_setting('server_version_num')::int AS version_num"
        ).fetchone()
        require(
            row["database"] == self.request.database and row["role"] == self.request.database + "_" + role,
            "DATABASE_IDENTITY",
        )
        require(row["host"] in {"127.0.0.1", "::1"} and row["port"] == 5432, "LOOPBACK_ONLY")
        require(150000 <= row["version_num"] < 160000, "POSTGRES15_REQUIRED")
        return row

    def _runtime_safe(self, connection: Any) -> bool:
        row = connection.execute(
            "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls "
            "OR has_database_privilege(current_user,current_database(),'CREATE') "
            "OR has_database_privilege(current_user,current_database(),'TEMP') "
            "OR has_schema_privilege(current_user,'mingjing_core','CREATE') "
            "OR has_schema_privilege(current_user,'public','CREATE') "
            "OR EXISTS(SELECT 1 FROM pg_auth_members "
            "WHERE member=(SELECT oid FROM pg_roles WHERE rolname=current_user)) "
            "OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname IN ('mingjing_core','public') "
            "AND pg_has_role(current_user,c.relowner,'USAGE')) "
            "OR EXISTS(SELECT 1 FROM pg_tables t WHERE t.schemaname IN ('mingjing_core','public') "
            "AND has_table_privilege(current_user,quote_ident(t.schemaname)||'.'||quote_ident(t.tablename),"
            "'TRUNCATE,REFERENCES,TRIGGER')) AS elevated "
            "FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        require(row is not None, "RUNTIME_ROLE_MISSING")
        safe = not row["elevated"]
        for table in (
            "mingjing_core.schema_migrations",
            "public.checkpoint_migrations",
        ):
            rights = connection.execute(
                "SELECT has_table_privilege(current_user,%s,'SELECT') AND NOT "
                "has_table_privilege(current_user,%s,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER') AS safe",
                (table, table),
            ).fetchone()
            safe = safe and rights["safe"]
        tables = connection.execute(
            "SELECT schemaname||'.'||tablename AS name FROM pg_tables WHERE "
            "schemaname='mingjing_core' AND tablename<>'schema_migrations' OR "
            "schemaname='public' AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes')"
        ).fetchall()
        for table in tables:
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                allowed = connection.execute(
                    "SELECT has_table_privilege(current_user,%s,%s) AS safe",
                    (table["name"], privilege),
                ).fetchone()
                safe = safe and allowed["safe"]
        return bool(safe)

    def _new_tables(self, connection: Any, migrated: bool) -> bool:
        if not migrated:
            return False
        for name in ("core_run_steps", "core_run_events", "core_embeddings"):
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                row = connection.execute(
                    "SELECT has_table_privilege(current_user,%s,%s) AS allowed",
                    ("mingjing_core." + name, privilege),
                ).fetchone()
                if row["allowed"] is not True:
                    return False
        return True

    def _state(self, connection: Any) -> str:
        tables = connection.execute(
            "SELECT schemaname,tablename FROM pg_tables WHERE schemaname='mingjing_core' "
            "OR schemaname='public' AND tablename IN ('checkpoints','checkpoint_blobs','checkpoint_writes',"
            "'checkpoint_migrations') ORDER BY schemaname,tablename"
        ).fetchall()
        hashes = {}
        for row in tables:
            query = sql.SQL(
                "SELECT encode(sha256(convert_to(coalesce(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),"
                "'[]'::jsonb)::text,'UTF8')),'hex') AS hash FROM {}.{} t"
            ).format(sql.Identifier(row["schemaname"]), sql.Identifier(row["tablename"]))
            hashes[row["schemaname"] + "." + row["tablename"]] = connection.execute(query).fetchone()["hash"]
        return digest(hashes)

    def snapshot(self, *, migrated: bool) -> dict[str, Any]:
        identities = {}
        with self._connection("writer") as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL statement_timeout='5s'")
            identities["writer"] = self._identity(connection, "writer")
            safe, new_tables = (
                self._runtime_safe(connection),
                self._new_tables(connection, migrated),
            )
        with self._connection("owner") as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            connection.execute("SET LOCAL statement_timeout='5s'")
            identities["owner"] = self._identity(connection, "owner")
            checksums = {
                str(row["version"]): row["checksum"]
                for row in connection.execute(
                    "SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version"
                ).fetchall()
            }
            queues = connection.execute(
                "SELECT count(*) FILTER(WHERE status='queued') AS queued,"
                "count(*) FILTER(WHERE status='running') AS running,"
                "count(*) FILTER(WHERE lease_until>now()) AS leases FROM mingjing_core.core_runs"
            ).fetchone()
            sessions = connection.execute(
                "SELECT count(*) AS count FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid() AND backend_type='client backend'"
            ).fetchone()["count"]
            state = self._state(connection)
        return {
            "identities": identities,
            "runtime_safe": safe,
            "new_tables_crud": new_tables,
            "checksums": checksums,
            "queues": queues,
            "other_database_sessions": sessions,
            "state_sha256": state,
        }

    def environment(self) -> dict[str, str]:
        self.dsns = _controlled_dsns(self.request, self.dsns)
        env = {key: os.environ[key] for key in ("PATH", "LANG", "SYSTEMROOT") if key in os.environ}
        env.update(
            CORE_INCREMENTAL_OWNER_DSN=self.dsns["owner"],
            CORE_INCREMENTAL_WRITER_DSN=self.dsns["writer"],
            CORE_INCREMENTAL_DATABASE=self.request.database,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONNOUSERSITE="1",
            PYTHONPYCACHEPREFIX="/root/zhiming-core-backups/incremental-pycache",
        )
        return env

    def candidate(self, body: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        prefix = "import sys,json,os\nsys.path.insert(0," + repr(self.request.release) + ")\n"
        prefix += "from mingjing_core.repositories.postgres import PostgresRepository\n"
        raw = self.runner.run(
            [
                self.request.release + "/venv/core/bin/python",
                "-I",
                "-B",
                "-X",
                "pycache_prefix=" + os.path.abspath(os.devnull),
                "-c",
                prefix + body,
            ],
            env=self.environment(),
            stdin=json.dumps(payload or {}),
        )
        result = json.loads(raw)
        require(isinstance(result, dict), "CANDIDATE_RECEIPT")
        return result

    def migrate_and_grant(self) -> None:
        body = """from psycopg.conninfo import conninfo_to_dict
from mingjing_core.repositories.permissions import grant_runtime_tables
from mingjing_core.repositories.foundation import migration_manifest
if set(migration_manifest()) != set(range(1,8)): raise RuntimeError('PINNED_MIGRATIONS')
repo=PostgresRepository(os.environ['CORE_INCREMENTAL_OWNER_DSN'],schema='mingjing_core')
try:
    repo.verify_schema()
    with repo.connection() as c:
        grant_runtime_tables(c,conninfo_to_dict(os.environ['CORE_INCREMENTAL_WRITER_DSN'])['user'])
finally: repo.close()
print(json.dumps({'migrated':True}))
"""
        require(self.candidate(body).get("migrated") is True, "MIGRATION_RECEIPT")

    def backfill(self, owner: str, *, apply: bool) -> dict[str, Any]:
        body = """from mingjing_core.application.memory import MemoryService
from mingjing_core.memory.backfill import backfill
from mingjing_core.repositories.postgres import fingerprint
from psycopg import sql
args=json.load(sys.stdin)
repo=PostgresRepository(os.environ['CORE_INCREMENTAL_OWNER_DSN'],initialize=False)
def originals():
    with repo.connection() as c:
        rows=c.execute(sql.SQL("SELECT kind,id,subject,case_id,status,revision,created_at,"
            "data-'search_tokens'-'thread_id'-'at_ms'-'origin_conversation_id' AS original "
            "FROM {} WHERE owner=%s ORDER BY kind,id").format(repo.table('core_entities')),
            (args['owner'],)).fetchall()
    return {(row['kind'],row['id']):fingerprint(row) for row in rows}
try:
    repo.verify_schema()
    with repo.transaction(args['owner']):
        before=originals()
        result=backfill(MemoryService(repo),args['owner'],apply=args['apply'])
        after=originals()
        if any(after.get(key)!=value for key,value in before.items()): raise RuntimeError('ORIGINAL_CHANGED')
    result['immutable_originals_preserved']=True
    result['sample_ids']=[fingerprint(value) for value in result.get('sample_ids',[])]
finally: repo.close()
print(json.dumps(result))
"""
        return self.candidate(body, {"owner": owner, "apply": apply})

    def dump(self, output: Path) -> None:
        env = self.environment()
        for key, name in (
            ("host", "PGHOST"),
            ("hostaddr", "PGHOSTADDR"),
            ("port", "PGPORT"),
            ("user", "PGUSER"),
            ("password", "PGPASSWORD"),
            ("dbname", "PGDATABASE"),
            ("passfile", "PGPASSFILE"),
            ("options", "PGOPTIONS"),
        ):
            value = conninfo_to_dict(self.dsns["owner"]).get(key)
            if value is not None:
                env[name] = value
        self.runner.run(
            ["pg_dump", "--format=custom", "--no-owner", "--no-acl"],
            env=env,
            output=output,
        )

    def withdrawals(self) -> dict[str, Any]:
        return self.candidate("""from tools.deploy_core import export_withdrawals
repo=PostgresRepository(os.environ['CORE_INCREMENTAL_OWNER_DSN'],initialize=False)
try: result=export_withdrawals(repo)
finally: repo.close()
print(json.dumps(result,default=str))
""")

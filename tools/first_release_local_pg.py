"""Create only a new test-owned database; failures retain all created objects."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from tools.first_release_contracts import require
from tools.first_release_local_inputs import LocalInputs


@dataclass(frozen=True)
class _Birth:
    creator: Any = field(repr=False)
    operation: str
    database: str
    database_oid: int
    owner_oid: int
    writer_oid: int
    backend_pid: int


_BIRTHS: dict[int, _Birth] = {}


def _birth_identity(inputs: LocalInputs, creator: Any) -> _Birth:
    record = _BIRTHS.get(id(creator))
    require(
        isinstance(creator, psycopg.Connection)
        and not creator.closed
        and record is not None
        and record.creator is creator
        and record.operation == inputs.contract.operation_id
        and record.database == inputs.contract.database
        and record.backend_pid == creator.pgconn.backend_pid,
        "LOCAL_TARGET_LIVE_CREATION_REQUIRED",
    )
    return record


def server_identity(connection: Any, fields: dict[str, str]) -> None:
    row = connection.execute(
        "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
        "host(inet_server_addr()) AS host,inet_server_port() AS port,"
        "current_setting('server_version_num')::int AS version_num"
    ).fetchone()
    require(
        row["database"] == fields["dbname"] and row["role"] == fields["user"] and row["session_role"] == row["role"],
        "LOCAL_ACTUAL_IDENTITY_MISMATCH",
    )
    require(row["host"] == fields["host"] and row["port"] == int(fields["port"]), "LOCAL_ACTUAL_SERVER_MISMATCH")
    require(row["port"] in {55480, 55481} and 150000 <= row["version_num"] < 160000, "LOCAL_POSTGRES15_REQUIRED")


@contextmanager
def new_target(inputs: LocalInputs, dsns: dict[str, str]) -> Iterator[Any]:
    fields = conninfo_to_dict(dsns["admin"])
    with psycopg.connect(dsns["admin"], autocommit=True, row_factory=dict_row) as admin:
        admin.execute("SET search_path=pg_catalog")
        server_identity(admin, fields)
        locked = admin.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok",
            ("first-release-local:" + inputs.contract.database,),
        ).fetchone()["ok"]
        require(locked, "LOCAL_RESTORE_ALREADY_RUNNING")
        try:
            create_target(admin, inputs, dsns)
            initialize_public(inputs, dsns)
            # Closing this session releases the lock; no cleanup/retry removes a partial restore.
            yield admin
        finally:
            _BIRTHS.pop(id(admin), None)


def create_target(admin: Any, inputs: LocalInputs, dsns: dict[str, str]) -> None:
    require(id(admin) not in _BIRTHS, "LOCAL_TARGET_CREATOR_ALREADY_REGISTERED")
    name = inputs.contract.database
    roles = [name + "_owner", name + "_writer"]
    exists = admin.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_database WHERE datname=%s) OR "
        "EXISTS(SELECT 1 FROM pg_roles WHERE rolname=ANY(%s)) AS present",
        (name, roles),
    ).fetchone()["present"]
    require(not exists, "LOCAL_DATABASE_OR_ROLE_ALREADY_EXISTS")
    role_oids = _create_roles(admin, dsns)
    admin.execute(
        sql.SQL("CREATE DATABASE {} OWNER {} TEMPLATE template0 ENCODING 'UTF8'").format(
            sql.Identifier(name), sql.Identifier(roles[0])
        )
    )
    database = admin.execute("SELECT oid,datdba FROM pg_database WHERE datname=%s", (name,)).fetchone()
    require(database and database["datdba"] == role_oids["owner"], "LOCAL_TARGET_CREATED_OWNER_CHANGED")
    _BIRTHS[id(admin)] = _Birth(
        admin,
        inputs.contract.operation_id,
        name,
        database["oid"],
        role_oids["owner"],
        role_oids["writer"],
        admin.pgconn.backend_pid,
    )
    admin.execute(sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name)))
    admin.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {},{}").format(
            sql.Identifier(name), sql.Identifier(roles[0]), sql.Identifier(roles[1])
        )
    )


def _create_roles(admin: Any, dsns: dict[str, str]) -> dict[str, int]:
    with admin.transaction():
        result = {}
        for role in ("owner", "writer"):
            fields = conninfo_to_dict(dsns[role])
            password = fields.get("password")
            verifier = None
            if password is not None:
                verifier = admin.pgconn.encrypt_password(
                    password.encode("utf-8"), fields["user"].encode("utf-8"), b"scram-sha-256"
                ).decode("ascii")
                require(verifier.startswith("SCRAM-SHA-256$"), "LOCAL_ROLE_VERIFIER_REJECTED")
            # Even DDL statement logging must never receive the original password.
            admin.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(fields["user"]), sql.Literal(verifier))
            )
            row = admin.execute("SELECT oid FROM pg_roles WHERE rolname=%s", (fields["user"],)).fetchone()
            require(row is not None, "LOCAL_TARGET_CREATED_ROLE_MISSING")
            result[role] = row["oid"]
    return result


def initialize_public(inputs: LocalInputs, dsns: dict[str, str]) -> None:
    # NOINHERIT deliberately prevents using pg_database_owner's default schema rights.
    target = make_conninfo(dsns["admin"], dbname=inputs.contract.database)
    with psycopg.connect(target, row_factory=dict_row) as admin:
        admin.execute("SET LOCAL search_path=pg_catalog")
        server_identity(admin, conninfo_to_dict(target))
        owner = inputs.contract.database + "_owner"
        actual = admin.execute(
            "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
        ).fetchone()["owner"]
        require(actual == owner, "NEW_LOCAL_DATABASE_OWNER_CHANGED")
        public = admin.execute(
            "SELECT pg_get_userbyid(n.nspowner) AS owner,"
            "(SELECT count(*) FROM pg_class WHERE relnamespace=n.oid)+"
            "(SELECT count(*) FROM pg_proc WHERE pronamespace=n.oid)+"
            "(SELECT count(*) FROM pg_type WHERE typnamespace=n.oid) AS objects "
            "FROM pg_namespace n WHERE nspname='public'"
        ).fetchone()
        require(
            public and public["owner"] == "pg_database_owner" and public["objects"] == 0,
            "NEW_LOCAL_PUBLIC_NOT_EMPTY_DEFAULT",
        )
        admin.execute(sql.SQL("ALTER SCHEMA public OWNER TO {}").format(sql.Identifier(owner)))


def verify_original(inputs: LocalInputs, owner_dsn: str) -> dict[str, Any]:
    fields = conninfo_to_dict(owner_dsn)
    with psycopg.connect(owner_dsn, autocommit=True, row_factory=dict_row) as connection, connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        server_identity(connection, fields)
        roles = connection.execute(
            "SELECT rolname,rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR "
            "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) AS unsafe "
            "FROM pg_roles WHERE rolname=ANY(%s)",
            ([inputs.contract.database + "_owner", inputs.contract.database + "_writer"],),
        ).fetchall()
        require(len(roles) == 2 and not any(row["unsafe"] for row in roles), "LOCAL_RESTORE_ROLES_UNSAFE")
        owner = connection.execute(
            "SELECT pg_get_userbyid(datdba) AS owner FROM pg_database WHERE datname=current_database()"
        ).fetchone()["owner"]
        require(owner == fields["user"], "LOCAL_DATABASE_OWNER_MISMATCH")
        schemas = connection.execute(
            "SELECT nspname,pg_get_userbyid(nspowner) AS owner FROM pg_namespace "
            "WHERE nspname IN ('mingjing_core','public')"
        ).fetchall()
        require(
            len(schemas) == 2 and all(row["owner"] == fields["user"] for row in schemas), "LOCAL_SCHEMA_OWNER_MISMATCH"
        )
        objects = connection.execute(
            "SELECT n.nspname,c.relname,pg_get_userbyid(c.relowner) AS owner FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('mingjing_core','public')"
        ).fetchall()
        require(objects and all(row["owner"] == fields["user"] for row in objects), "LOCAL_OBJECT_OWNER_MISMATCH")
        require(
            not any(
                row["relname"]
                in {"core_model_accounts", "core_model_usage", "core_model_batches", "core_model_authorizations"}
                for row in objects
            ),
            "CENTRAL_LEDGER_NOT_SUPPORTED",
        )
        rows = connection.execute(
            "SELECT version,checksum FROM mingjing_core.schema_migrations ORDER BY version"
        ).fetchall()
        actual = {str(row["version"]): row["checksum"] for row in rows}
        require(actual == dict(inputs.dump_pin.source_migrations), "RESTORED_ORIGINAL_PREFIX_MISMATCH")
    return {
        "original_prefix": actual,
        "objects_checked": len(objects),
        "original_prefix_verified": True,
        "ownership_verified": True,
        "central_ledger_present": False,
    }

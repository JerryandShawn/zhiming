"""Explicit service writer identity; no administrator credentials or provisioning."""

from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg.conninfo import conninfo_to_dict

from tools.first_release_contracts import ordinary, require

ROOT = Path(__file__).absolute().parents[1]
ROLES = frozenset({"web", "feishu", "report", "hermes"})


@dataclass(frozen=True)
class ServiceBinding:
    role: str
    candidate: Path
    workspace: Path
    system_identifier: str
    database: str
    database_oid: int
    writer: str
    writer_oid: int

    @property
    def fence_path(self) -> Path:
        return self.workspace / "private/first-release-writers" / f"{self.system_identifier}-{self.database_oid}.lock"

    @property
    def fence_key(self) -> str:
        return f"first-release-writer:{self.system_identifier}:{self.database_oid}"

    @property
    def maintenance(self) -> Path:
        return self.fence_path.with_suffix(".maintenance.json")

    def validate(self, native_args: list[str]) -> None:
        require(self.role in ROLES, "SERVICE_ROLE_REJECTED")
        ordinary(self.candidate, directory=True)
        ordinary(self.workspace, directory=True)
        require(self.candidate == ROOT, "SERVICE_CURRENT_CANDIDATE_REQUIRED")
        for relative in (
            "tools/first_release_service.py",
            "tools/first_release_service_binding.py",
            "mingjing_core/__init__.py",
        ):
            ordinary(self.candidate / relative)
        require(bool(re.fullmatch(r"[0-9]{15,20}", self.system_identifier)), "SERVICE_SYSTEM_IDENTIFIER_REJECTED")
        require(
            all(type(value) is int and 0 < value < 2**32 for value in (self.database_oid, self.writer_oid)),
            "SERVICE_OIDS_REJECTED",
        )
        require(
            all(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", value)) for value in (self.database, self.writer)),
            "SERVICE_DATABASE_OR_WRITER_REJECTED",
        )
        require(
            type(native_args) is list
            and len(native_args) <= 128
            and all(isinstance(value, str) and "\x00" not in value for value in native_args)
            and sum(len(value) for value in native_args) <= 16_000
            and (self.role in {"report", "hermes"} or not native_args),
            "SERVICE_NATIVE_ARGUMENTS_REJECTED",
        )
        ordinary(self.fence_path.parent, directory=True)
        ordinary(self.fence_path)
        require(not self.maintenance.is_symlink(), "SERVICE_LINKED_MAINTENANCE_REJECTED")
        if os.path.lexists(self.maintenance):
            ordinary(self.maintenance)


def writer_parameters(binding: ServiceBinding) -> dict[str, Any]:
    require(
        not any(key.startswith("PG") and value for key, value in os.environ.items()), "SERVICE_IMPLICIT_PG_REJECTED"
    )
    dsn = os.environ.get("ZHIMING_DATABASE_URL", "")
    require(bool(dsn), "SERVICE_EXPLICIT_WRITER_DSN_REQUIRED")
    fields = conninfo_to_dict(dsn)
    require(
        set(fields) <= {"host", "port", "dbname", "user", "password", "connect_timeout", "sslmode"}
        and all(fields.get(key) for key in ("host", "port", "dbname", "user", "password")),
        "SERVICE_DSN_ROUTING_REJECTED",
    )
    try:
        address, port = ipaddress.ip_address(fields["host"]), int(fields["port"])
    except ValueError:
        require(False, "SERVICE_EXPLICIT_TCP_REQUIRED")
    require(0 < port <= 65535 and fields["port"] == str(port), "SERVICE_EXPLICIT_TCP_REQUIRED")
    require(fields["dbname"] == binding.database and fields["user"] == binding.writer, "SERVICE_DSN_IDENTITY_REJECTED")
    require(
        fields.get("sslmode", "disable") in {"disable", "require", "verify-ca", "verify-full"}, "SERVICE_SSL_REJECTED"
    )
    return {
        **fields,
        "host": str(address),
        "connect_timeout": 5,
        "sslmode": fields.get("sslmode", "disable"),
        "application_name": "first_release_service",
        "client_encoding": "UTF8",
        "passfile": os.devnull,
    }


def checked_writer(connection: Any, binding: ServiceBinding, parameters: dict[str, Any]) -> None:
    with connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        connection.execute("SET LOCAL search_path=pg_catalog")
        row = connection.execute(
            "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
            "host(inet_server_addr()) AS host,inet_server_port() AS port,"
            "current_setting('server_version_num')::int AS version,"
            "(SELECT oid FROM pg_database WHERE datname=current_database()) AS database_oid,"
            "(SELECT datdba FROM pg_database WHERE datname=current_database()) AS owner_oid,"
            "r.oid AS role_oid,r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication "
            "OR r.rolbypassrls OR r.rolinherit OR NOT r.rolcanlogin "
            "OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid) AS unsafe "
            "FROM pg_roles r WHERE r.rolname=current_user"
        ).fetchone()
        require(
            row
            and row["database"] == binding.database
            and row["database_oid"] == binding.database_oid
            and row["role"] == row["session_role"] == binding.writer
            and row["role_oid"] == binding.writer_oid
            and row["owner_oid"] != binding.writer_oid,
            "SERVICE_ACTUAL_IDENTITY_REJECTED",
        )
        require(
            not row["unsafe"]
            and 150000 <= row["version"] < 160000
            and ipaddress.ip_address(row["host"]) == ipaddress.ip_address(parameters["host"])
            and row["port"] == int(parameters["port"])
            and connection.info.host == parameters["host"]
            and connection.info.port == int(parameters["port"]),
            "SERVICE_ACTUAL_LOCATION_OR_ROLE_REJECTED",
        )
        require(
            connection.execute("SELECT system_identifier::text AS sid FROM pg_catalog.pg_control_system()").fetchone()[
                "sid"
            ]
            == binding.system_identifier,
            "SERVICE_ACTUAL_SYSTEM_IDENTIFIER_REJECTED",
        )
        restricted_writer(connection)


def restricted_writer(connection: Any) -> None:
    row = connection.execute(
        "SELECT has_database_privilege(current_user,current_database(),'CREATE') OR "
        "has_database_privilege(current_user,current_database(),'TEMP') OR "
        "EXISTS(SELECT 1 FROM pg_namespace WHERE nspname IN ('mingjing_core','public') "
        "AND has_schema_privilege(current_user,oid,'CREATE')) OR "
        "EXISTS(SELECT 1 FROM pg_namespace WHERE nspowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR "
        "EXISTS(SELECT 1 FROM pg_class WHERE relowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) OR "
        "EXISTS(SELECT 1 FROM pg_proc WHERE proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)) AS unsafe"
    ).fetchone()
    require(not row["unsafe"], "SERVICE_WRITER_OWNERSHIP_OR_DDL_REJECTED")

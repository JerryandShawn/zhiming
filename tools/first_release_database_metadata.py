"""Capture and reapply database metadata without updating PostgreSQL catalogs directly."""

from __future__ import annotations

import re
from typing import Any

from psycopg import sql

from tools.first_release_contracts import require


def _acl(connection: Any, database: str) -> list[dict[str, Any]]:
    return connection.execute(
        "SELECT a.grantor::int,pg_catalog.pg_get_userbyid(a.grantor) AS grantor_name,"
        "a.grantee::int,CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(a.grantee) END "
        "AS grantee_name,a.privilege_type,a.is_grantable FROM pg_catalog.pg_database d "
        "CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(d.datacl,pg_catalog.acldefault('d',d.datdba))) a "
        "WHERE d.datname=%s ORDER BY a.grantor,a.grantee,a.privilege_type",
        (database,),
    ).fetchall()


def _settings(connection: Any, oid: int) -> list[dict[str, Any]]:
    return connection.execute(
        "SELECT s.setrole::int AS role_oid,CASE WHEN s.setrole=0 THEN NULL "
        "ELSE pg_catalog.pg_get_userbyid(s.setrole) END AS role_name,v AS setting "
        "FROM pg_catalog.pg_db_role_setting s CROSS JOIN LATERAL pg_catalog.unnest(s.setconfig) v "
        "WHERE s.setdatabase=%s ORDER BY s.setrole,v",
        (oid,),
    ).fetchall()


def capture(connection: Any, database: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT d.oid::int,d.datname AS database,d.datdba::int AS owner_oid,"
        "pg_catalog.pg_get_userbyid(d.datdba) AS owner,pg_catalog.pg_encoding_to_char(d.encoding) AS encoding,"
        "d.datcollate AS collate,d.datctype AS ctype,d.datlocprovider AS locale_provider,"
        "d.datconnlimit AS connection_limit,d.datistemplate AS is_template "
        "FROM pg_catalog.pg_database d WHERE d.datname=%s",
        (database,),
    ).fetchone()
    require(row is not None, "EXCHANGE_DATABASE_MISSING")
    require(row["locale_provider"] == "c" and not row["is_template"], "EXCHANGE_DATABASE_LOCALE_UNSUPPORTED")
    sid = connection.execute("SELECT system_identifier::text FROM pg_catalog.pg_control_system()").fetchone()
    return {
        "schema": "first-release-database-metadata-v1",
        "system_identifier": sid["system_identifier"],
        **row,
        "acl": _acl(connection, database),
        "settings": _settings(connection, row["oid"]),
    }


def validate(connection: Any, snapshot: dict[str, Any]) -> None:
    require(snapshot.get("schema") == "first-release-database-metadata-v1", "EXCHANGE_METADATA_SCHEMA")
    require(
        all(row["grantor"] == snapshot["owner_oid"] for row in snapshot["acl"]),
        "EXCHANGE_MULTI_GRANTOR_REQUIRES_REVIEW",
    )
    roles = {snapshot["owner_oid"]: snapshot["owner"]}
    for row in snapshot["acl"]:
        require(row["privilege_type"] in {"CREATE", "CONNECT", "TEMPORARY"}, "EXCHANGE_ACL_PRIVILEGE")
        if row["grantee"]:
            roles[row["grantee"]] = row["grantee_name"]
    for row in snapshot["settings"]:
        key, separator, _ = row["setting"].partition("=")
        require(
            separator
            and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", key)
            and key not in {"role", "session_authorization", "is_superuser"},
            "EXCHANGE_SETTING_REQUIRES_REVIEW",
        )
        if row["role_oid"]:
            roles[row["role_oid"]] = row["role_name"]
    for oid, name in roles.items():
        observed = connection.execute("SELECT rolname FROM pg_catalog.pg_roles WHERE oid=%s", (oid,)).fetchone()
        require(observed is not None and observed["rolname"] == name, "EXCHANGE_ROLE_IDENTITY_CHANGED")


def semantic(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in snapshot.items() if key not in {"oid", "database"}}


def _grantee(row: dict[str, Any]) -> sql.Composable:
    return sql.SQL("PUBLIC") if row["grantee"] == 0 else sql.Identifier(row["grantee_name"])


def apply_metadata(connection: Any, database: str, snapshot: dict[str, Any]) -> None:
    validate(connection, snapshot)
    target = sql.Identifier(database)
    connection.execute(sql.SQL("ALTER DATABASE {} OWNER TO {}").format(target, sql.Identifier(snapshot["owner"])))
    connection.execute(
        sql.SQL("ALTER DATABASE {} CONNECTION LIMIT {}").format(target, sql.Literal(snapshot["connection_limit"]))
    )
    existing = _acl(connection, database)
    connection.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(snapshot["owner"])))
    for row in {item["grantee"]: item for item in existing}.values():
        connection.execute(sql.SQL("REVOKE ALL PRIVILEGES ON DATABASE {} FROM {}").format(target, _grantee(row)))
    for row in snapshot["acl"]:
        suffix = sql.SQL(" WITH GRANT OPTION") if row["is_grantable"] else sql.SQL("")
        connection.execute(
            sql.SQL("GRANT {} ON DATABASE {} TO {}{}").format(
                sql.SQL(row["privilege_type"]),
                target,
                _grantee(row),
                suffix,
            )
        )
    connection.execute("RESET ROLE")
    for row in _settings(connection, capture(connection, database)["oid"]):
        require(row in snapshot["settings"], "EXCHANGE_UNEXPECTED_TARGET_SETTINGS")
    for row in snapshot["settings"]:
        key, _, value = row["setting"].partition("=")
        connection.execute("SELECT pg_catalog.set_config(%s,%s,true)", (key, value))
        statement = sql.SQL("ALTER DATABASE {} SET {} FROM CURRENT").format(target, sql.Identifier(key))
        if row["role_oid"]:
            statement = sql.SQL("ALTER ROLE {} IN DATABASE {} SET {} FROM CURRENT").format(
                sql.Identifier(row["role_name"]),
                target,
                sql.Identifier(key),
            )
        connection.execute(statement)
    require(semantic(capture(connection, database)) == semantic(snapshot), "EXCHANGE_METADATA_REAPPLY_FAILED")

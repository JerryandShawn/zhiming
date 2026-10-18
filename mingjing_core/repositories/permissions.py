"""Reapply DML-only grants after forward migrations create new tables."""

from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg import sql

if TYPE_CHECKING:
    # This deployment boundary accepts both tuple-row and dict-row connections.
    from typing import Any

    from psycopg import Connection


def grant_runtime_tables(connection: Connection[Any], role_name: str, schema: str = "mingjing_core") -> list[str]:
    role, namespace = sql.Identifier(role_name), sql.Identifier(schema)
    connection.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(namespace, role))
    connection.execute(
        sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO {}").format(namespace, role)
    )
    connection.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO {}").format(namespace, role))
    connection.execute(sql.SQL("REVOKE INSERT,UPDATE,DELETE ON {}.schema_migrations FROM {}").format(namespace, role))
    connection.execute(sql.SQL("REVOKE CREATE ON SCHEMA {} FROM {}").format(namespace, role))
    tables = ["core_run_steps", "core_run_events", "core_embeddings"]
    for table in tables:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            allowed = connection.execute(
                "SELECT has_table_privilege(%s,%s,%s)",
                (role_name, f'"{schema}"."{table}"', privilege),
            ).fetchone()
            result = next(iter(allowed.values())) if isinstance(allowed, dict) else allowed[0]
            if not result:
                raise RuntimeError("迁移后的运行角色授权不完整")
    _grant_quota_tables(connection, role_name, schema)
    return tables


def _grant_quota_tables(connection: Connection[Any], role_name: str, schema: str) -> None:
    present = connection.execute("SELECT to_regclass(%s)", (f'"{schema}"."core_model_usage"',)).fetchone()
    if not (next(iter(present.values())) if isinstance(present, dict) else present[0]):
        return
    role, namespace = sql.Identifier(role_name), sql.Identifier(schema)
    privileges = {
        "core_model_accounts": ("SELECT", "UPDATE"),
        "core_model_usage": ("SELECT", "INSERT", "UPDATE"),
        "core_model_batches": ("SELECT", "INSERT", "UPDATE"),
        "core_model_authorizations": ("SELECT", "INSERT"),
    }
    for table, allowed in privileges.items():
        target = sql.SQL("{}.{}").format(namespace, sql.Identifier(table))
        connection.execute(sql.SQL("REVOKE INSERT,UPDATE,DELETE ON {} FROM {}").format(target, role))
        connection.execute(sql.SQL("GRANT {} ON {} TO {}").format(sql.SQL(",".join(allowed)), target, role))
        for privilege in allowed:
            row = connection.execute(
                "SELECT has_table_privilege(%s,%s,%s)",
                (role_name, f'"{schema}"."{table}"', privilege),
            ).fetchone()
            if not (next(iter(row.values())) if isinstance(row, dict) else row[0]):
                raise RuntimeError("中央守卫运行角色授权不完整")

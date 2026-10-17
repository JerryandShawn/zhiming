"""Reapply DML-only grants after forward migrations create new tables."""

from psycopg import sql


def grant_runtime_tables(connection, role_name: str, schema: str = "mingjing_core") -> list[str]:
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
                "SELECT has_table_privilege(%s,%s,%s)", (role_name, f'"{schema}"."{table}"', privilege)
            ).fetchone()
            result = next(iter(allowed.values())) if isinstance(allowed, dict) else allowed[0]
            if not result:
                raise RuntimeError("迁移后的运行角色授权不完整")
    return tables

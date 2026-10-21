"""Real loopback PG permission SQL; never a NativePort or stage connection."""

from __future__ import annotations

import psycopg
import pytest
from b1_restore_proof_support import Fixture, proof_db
from psycopg import sql
from psycopg.rows import dict_row
from test_b1_restore_proof_pg import prepare

from tools.b1_restore_proof import generate
from tools.core_incremental_pg import PostgresPort

__all__ = ["proof_db"]


def actual_safe(value: Fixture) -> bool:
    # Exercise only this method's real SQL. No controller DSN/connector or stage identity is constructed.
    probe = object.__new__(PostgresPort)
    with psycopg.connect(value.writer_dsn, row_factory=dict_row) as connection:
        return probe._runtime_safe(connection)


@pytest.mark.parametrize("recipient", ["writer", "public"])
def test_temp_ddl_alone_refuses_incremental_writer_and_revoke_restores_safety(proof_db, recipient):
    prepare(proof_db)
    assert generate(proof_db.request)["admissible"] is False
    assert actual_safe(proof_db) is True
    target = sql.Identifier(proof_db.request.database)
    role = sql.Identifier(proof_db.request.database + "_writer") if recipient == "writer" else sql.SQL("PUBLIC")
    with psycopg.connect(proof_db.owner_dsn) as owner:
        owner.execute(sql.SQL("GRANT TEMP ON DATABASE {} TO {}").format(target, role))
    try:
        with psycopg.connect(proof_db.writer_dsn) as writer:
            assert writer.execute("SELECT has_database_privilege(current_user,current_database(),'TEMP')").fetchone()[0]
        assert actual_safe(proof_db) is False
    finally:
        with psycopg.connect(proof_db.owner_dsn) as owner:
            owner.execute(sql.SQL("REVOKE TEMP ON DATABASE {} FROM {}").format(target, role))
    assert actual_safe(proof_db) is True

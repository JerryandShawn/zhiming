"""Missing effective schema access has a stable refusal without changing production ACLs."""

from __future__ import annotations

import psycopg
import pytest
from b1_restore_proof_support import Fixture, proof_db
from psycopg import sql
from test_b1_incremental_runtime_temp_pg import actual_safe
from test_b1_restore_proof_pg import prepare

from tools.b1_restore_proof import generate
from tools.b1_restore_proof_pg import writer_permissions
from tools.b1_restore_replay_contracts import ReplayRejected

__all__ = ["proof_db"]


def effective_usage(value: Fixture, namespace: str) -> bool:
    with psycopg.connect(value.writer_dsn) as writer:
        return writer.execute("SELECT has_schema_privilege(current_user,%s,'USAGE')", (namespace,)).fetchone()[0]


def observations(value: Fixture) -> dict[str, bool | str]:
    try:
        native = actual_safe(value)
    except psycopg.errors.InsufficientPrivilege:
        native = "sql_insufficient_privilege"
    try:
        receipt = writer_permissions(value.request)
    except ReplayRejected as error:
        assert str(error) == "WRITER_OWNERSHIP_OR_DDL"
        restore = False
    except psycopg.errors.InsufficientPrivilege:
        restore = "sql_insufficient_privilege"
    else:
        assert receipt["forbidden_probes_denied"] == 5
        restore = True
    return {"incremental_safe": native, "restore_safe": restore}


@pytest.mark.parametrize("namespace", ["mingjing_core", "public"])
@pytest.mark.parametrize("source", ["writer", "public"])
def test_missing_effective_usage_refuses_both_permission_gates(proof_db, namespace, source):
    prepare(proof_db)
    assert generate(proof_db.request)["admissible"] is False
    writer = sql.Identifier(proof_db.request.database + "_writer")
    public = sql.SQL("PUBLIC")
    chosen, other = (writer, public) if source == "writer" else (public, writer)
    identifier = sql.Identifier(namespace)
    with psycopg.connect(proof_db.owner_dsn) as owner:
        owner.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(identifier, chosen))
        owner.execute(sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(identifier, other))
    assert effective_usage(proof_db, namespace) is True
    assert observations(proof_db) == {"incremental_safe": True, "restore_safe": True}
    with psycopg.connect(proof_db.owner_dsn) as owner:
        owner.execute(sql.SQL("REVOKE USAGE ON SCHEMA {} FROM {}").format(identifier, chosen))
    try:
        assert effective_usage(proof_db, namespace) is False
        assert observations(proof_db) == {"incremental_safe": False, "restore_safe": False}
    finally:
        with psycopg.connect(proof_db.owner_dsn) as owner:
            owner.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(identifier, chosen))
        assert effective_usage(proof_db, namespace) is True
        assert observations(proof_db) == {"incremental_safe": True, "restore_safe": True}

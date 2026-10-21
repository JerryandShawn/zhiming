"""Extra table privileges are unsafe even through PUBLIC; no production ACL changes."""

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


def observations(value: Fixture) -> dict[str, bool]:
    try:
        receipt = writer_permissions(value.request)
    except ReplayRejected as error:
        assert str(error) == "WRITER_OWNERSHIP_OR_DDL"
        restore = False
    else:
        assert receipt["forbidden_probes_denied"] == 5
        restore = True
    return {"incremental_safe": actual_safe(value), "restore_safe": restore}


@pytest.mark.parametrize("recipient", ["writer", "public"])
@pytest.mark.parametrize(
    ("namespace", "table", "privilege"),
    [
        ("mingjing_core", "core_entities", "TRIGGER"),
        ("mingjing_core", "core_entities", "REFERENCES"),
        ("mingjing_core", "core_entities", "TRUNCATE"),
        ("mingjing_core", "schema_migrations", "REFERENCES"),
        ("public", "checkpoint_migrations", "REFERENCES"),
    ],
)
def test_non_crud_table_privileges_refuse_both_permission_gates(proof_db, recipient, namespace, table, privilege):
    prepare(proof_db)
    assert generate(proof_db.request)["admissible"] is False
    assert observations(proof_db) == {"incremental_safe": True, "restore_safe": True}
    role = sql.Identifier(proof_db.request.database + "_writer") if recipient == "writer" else sql.SQL("PUBLIC")
    identifier = sql.Identifier(namespace, table)
    with psycopg.connect(proof_db.owner_dsn) as owner:
        owner.execute(sql.SQL("GRANT {} ON {} TO {}").format(sql.SQL(privilege), identifier, role))
    try:
        with psycopg.connect(proof_db.writer_dsn) as writer:
            assert writer.execute(
                "SELECT has_table_privilege(current_user,%s,%s)", (namespace + "." + table, privilege)
            ).fetchone()[0]
        assert observations(proof_db) == {"incremental_safe": False, "restore_safe": False}
    finally:
        with psycopg.connect(proof_db.owner_dsn) as owner:
            owner.execute(sql.SQL("REVOKE {} ON {} FROM {}").format(sql.SQL(privilege), identifier, role))
        assert observations(proof_db) == {"incremental_safe": True, "restore_safe": True}

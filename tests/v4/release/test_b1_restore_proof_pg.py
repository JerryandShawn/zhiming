"""Physical Windows PG15 restore evidence stays non-admissible for stage."""

from __future__ import annotations

import ast
import json
from dataclasses import replace

import psycopg
import pytest
from b1_restore_proof_support import ROOT, Fixture, backup, initialize4, proof_db, write

from tools.b1_restore_proof import generate, main
from tools.b1_restore_proof_contracts import LOCAL_SCHEMA
from tools.b1_restore_proof_pg import empty_target, writer_permissions
from tools.b1_restore_replay_contracts import ReplayRejected, file_hash
from tools.core_incremental_contracts import (
    MIGRATIONS,
    UpgradeRejected,
    validate_restore,
)

__all__ = ["proof_db"]


def prepare(value: Fixture, *, queued=False):
    initialize4(value)
    tree = ast.parse((ROOT / "tests/test_b1_restore_replay_pg.py").read_text(encoding="utf-8"))
    seed = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SEED" for target in node.targets)
    )
    ids = value.script(seed)
    if queued:
        with psycopg.connect(value.source_dsn) as conn:
            conn.execute("UPDATE mingjing_core.core_runs SET status='queued' WHERE id=%s", (ids["run"],))
    backup(value)
    document = value.script(
        """from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.application.memory import MemoryService
from mingjing_core.adapters.tarot import TarotService
from tools.deploy_core import export_withdrawals
repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'])
MemoryService(repo).retire_fact('primary',value['fact'],expected_revision=value['fact_revision'],scope='source')
TarotService(repo).delete('primary',value['draw'])
with repo.transaction('primary') as conn:
 conn.execute("UPDATE mingjing_core.delivery_outbox SET status='sent',receipt='om_synthetic_sent',"
              "attempts=1 WHERE id='b1-sent'")
 conn.execute("UPDATE mingjing_core.delivery_outbox SET status='sending',attempts=1 WHERE id='b1-uncertain'")
print(json.dumps(export_withdrawals(repo),default=str));repo.close()
""",
        **ids,
    )
    write(value.request.ledger, document)
    value.request = replace(value.request, ledger_sha256=file_hash(value.request.ledger))
    return ids


def test_real_dump_restore_migrate_replay_permissions_never_create_admissible_windows_proof(proof_db, capsys):
    ids = prepare(proof_db)
    output = proof_db.directory / "local-receipt.json"
    arguments = proof_db.arguments() + ["--apply", "--quiesced", "--output", str(output)]
    assert main(arguments) == 0
    receipt = json.loads(output.read_text())
    assert json.loads(capsys.readouterr().out)["admissible"] is False
    original_bytes = output.read_bytes()
    assert main(arguments) == 2
    assert "NEW_PROOF_OUTPUT_REQUIRED" in capsys.readouterr().err
    assert output.read_bytes() == original_bytes
    assert receipt["schema"] == LOCAL_SCHEMA and receipt["admissible"] is False
    assert receipt["actual_pg_restore"] and receipt["latest_withdrawals_replayed"]
    assert receipt["sent_uncertain_protected"] and receipt["runtime_safe"]
    assert receipt["checksums"] == MIGRATIONS and receipt["migration"]["forward_migrations"] == [5, 6, 7]
    assert receipt["replay_first"]["changed"] and receipt["replay_second"]["changed"] is False
    assert receipt["writer_permissions"]["forbidden_probes_denied"] == 5
    assert receipt["database_creation_observed"] is False and receipt["posix_permissions_verified"] is False
    assert receipt["created_at"].endswith("+08:00")
    upgrade, bound, _ = proof_db.request.validate()
    with pytest.raises(UpgradeRejected, match="RESTORE_PROOF_SCHEMA"):
        validate_restore(upgrade, bound, receipt)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        assert conn.execute(
            "SELECT data,status FROM mingjing_core.core_entities WHERE id=%s", (ids["source"],)
        ).fetchone() == ({}, "deleted")
        assert (
            conn.execute("SELECT count(*) FROM mingjing_core.tarot_draws WHERE id=%s", (ids["draw"],)).fetchone()[0]
            == 0
        )
        assert conn.execute("SELECT status FROM mingjing_core.delivery_outbox ORDER BY id").fetchall() == [
            ("sent",),
            ("uncertain",),
        ]
    assert receipt["model_calls"] == receipt["external_sends"] == 0


def test_nonempty_target_rejects_before_restore_and_does_not_clear_existing_rows(proof_db):
    with psycopg.connect(proof_db.owner_dsn) as conn:
        conn.execute("CREATE TABLE public.existing_synthetic(value int)")
        conn.execute("INSERT INTO public.existing_synthetic VALUES(37)")
    with pytest.raises(ReplayRejected, match="RESTORE_TARGET_NOT_EMPTY"):
        empty_target(proof_db.request)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        assert conn.execute("SELECT value FROM public.existing_synthetic").fetchone() == (37,)


@pytest.mark.parametrize("object_kind", ["enum", "namespace"])
def test_unknown_type_or_empty_namespace_blocks_restore_and_is_preserved(proof_db, monkeypatch, object_kind):
    from tools import b1_restore_proof

    prepare(proof_db)
    statements = {
        "enum": "CREATE TYPE public.existing_synthetic_enum AS ENUM ('synthetic')",
        "namespace": "CREATE SCHEMA existing_synthetic_schema",
    }
    with psycopg.connect(proof_db.owner_dsn) as conn:
        conn.execute(statements[object_kind])

    def forbidden(*args, **kwargs):
        pytest.fail("unknown preexisting object reached pg_restore")

    monkeypatch.setattr(b1_restore_proof, "restore_archive", forbidden)
    with pytest.raises(ReplayRejected, match="RESTORE_TARGET_NOT_EMPTY"):
        generate(proof_db.request)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        query = (
            "SELECT to_regtype('public.existing_synthetic_enum') IS NOT NULL"
            if object_kind == "enum"
            else "SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='existing_synthetic_schema')"
        )
        assert conn.execute(query).fetchone()[0]


def test_invalid_archive_returns_fixed_code_and_no_proof_without_echoing_bytes(proof_db, capsys):
    prepare(proof_db)
    proof_db.request.dump.write_bytes(b"PRIVATE_SYNTHETIC_DUMP_BODY_INVALID")
    bound = json.loads(proof_db.request.backup.read_text())
    bound["dump_sha256"] = file_hash(proof_db.request.dump)
    write(proof_db.request.backup, bound)
    output = proof_db.directory / "not-created.json"
    assert main(proof_db.arguments() + ["--apply", "--quiesced", "--output", str(output)]) == 2
    result = capsys.readouterr()
    assert "PG_RESTORE_FAILED" in result.err and "PRIVATE_SYNTHETIC" not in result.err
    assert not output.exists()
    empty_target(proof_db.request)


def test_restored_content_mismatch_never_migrates_and_retains_schema4_for_review(proof_db):
    prepare(proof_db)
    bound = json.loads(proof_db.request.backup.read_text())
    bound["source_state_sha256"] = "f" * 64
    write(proof_db.request.backup, bound)
    with pytest.raises(ReplayRejected, match="RESTORE_CONTENT_MISMATCH"):
        generate(proof_db.request)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        assert conn.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone()[0] == 4


@pytest.mark.parametrize("privilege", ["schema", "temporary"])
def test_writer_permissions_check_rejects_real_ddl_grant_after_valid_restore(proof_db, privilege):
    prepare(proof_db)
    generate(proof_db.request)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        from psycopg import sql

        role = sql.Identifier(proof_db.request.database + "_writer")
        statement = (
            sql.SQL("GRANT CREATE ON SCHEMA mingjing_core TO {}").format(role)
            if privilege == "schema"
            else sql.SQL("GRANT TEMP ON DATABASE {} TO {}").format(
                sql.Identifier(proof_db.request.database),
                role,
            )
        )
        conn.execute(statement)
    with pytest.raises(ReplayRejected, match="WRITER_OWNERSHIP_OR_DDL"):
        writer_permissions(proof_db.request)


def test_writer_permissions_reject_both_migration_ledgers_becoming_writable(proof_db):
    from psycopg import sql

    prepare(proof_db)
    generate(proof_db.request)
    for namespace, table in (("mingjing_core", "schema_migrations"), ("public", "checkpoint_migrations")):
        identifier = sql.Identifier(namespace, table)
        role = sql.Identifier(proof_db.request.database + "_writer")
        with psycopg.connect(proof_db.owner_dsn) as conn:
            conn.execute(sql.SQL("GRANT INSERT ON {} TO {}").format(identifier, role))
        with pytest.raises(ReplayRejected, match="WRITER_LEDGER_WRITABLE"):
            writer_permissions(proof_db.request)
        with psycopg.connect(proof_db.owner_dsn) as conn:
            conn.execute(sql.SQL("REVOKE INSERT ON {} FROM {}").format(identifier, role))
    assert writer_permissions(proof_db.request)["forbidden_probes_denied"] == 5


def test_other_target_session_refuses_empty_target_without_mutation(proof_db):
    with psycopg.connect(proof_db.owner_dsn), pytest.raises(ReplayRejected, match="OTHER_RESTORE_SESSIONS"):
        empty_target(proof_db.request)
    assert empty_target(proof_db.request)["database"] == proof_db.request.database


def test_active_restore_run_stops_before_forward_migration_even_if_latest_would_revoke_it(proof_db):
    prepare(proof_db, queued=True)
    with pytest.raises(ReplayRejected, match="RESTORE_NOT_QUIESCENT"):
        generate(proof_db.request)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        assert conn.execute("SELECT max(version) FROM mingjing_core.schema_migrations").fetchone()[0] == 4

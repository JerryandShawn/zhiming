"""Real Windows PG15 and fixed-b9 backfill, explicitly not a Linux proof."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest
from b1_restore_proof_support import SUPPORT, Fixture, proof_db
from psycopg.rows import dict_row

from tools.b1_linux_application_drill import execute
from tools.b1_linux_application_drill_contracts import DSN_ENV, ApplicationBlocked, ApplicationRequest
from tools.b1_linux_application_drill_process import run_worker
from tools.b1_linux_drill_sql import fixture_sql
from tools.b1_restore_proof_pg import state_hash

__all__ = ["proof_db"]


def prepare(value: Fixture, monkeypatch: pytest.MonkeyPatch) -> ApplicationRequest:
    SUPPORT["candidate"](
        value.request.candidate_source,
        "from mingjing_core.repositories.postgres import PostgresRepository\n"
        "repo=PostgresRepository(os.environ['B1_FIXTURE_DSN'])\n"
        "with repo.pool.connection() as conn:conn.execute(value['sql'])\n"
        "repo.close();print(json.dumps({'synthetic_initialized':True}))\n",
        value.owner_dsn,
        {"sql": fixture_sql()},
    )
    with psycopg.connect(value.owner_dsn) as conn:
        conn.execute(
            "UPDATE mingjing_core.core_runs SET request="
            '\'{"message":"synthetic original","source_message_id":"synthetic-message"}\'::jsonb,'
            "state_version='{\"message:synthetic-message\":1}'::jsonb,"
            "result='{\"answer\":\"SYNTHETIC_B1_LEGACY_REPLY\"}'::jsonb WHERE id='synthetic-run'"
        )
    monkeypatch.setenv(DSN_ENV, value.owner_dsn)
    return ApplicationRequest(
        "b1-application-synthetic", "backfill", value.request.candidate_source, Path(sys.executable), True
    )


def fingerprint(value: Fixture) -> str:
    with psycopg.connect(value.owner_dsn, row_factory=dict_row) as conn:
        return state_hash(conn)


def test_actual_primary_backfill_dry_apply_repeat_preserves_originals_and_secondary(proof_db, monkeypatch):
    request = prepare(proof_db, monkeypatch)
    output = proof_db.directory / "application-result.json"
    receipt = execute(request, output)
    result = receipt["result"]
    assert receipt["schema"] == "b1-local-application-drill-v1"
    assert receipt["admissible_linux"] is receipt["stage_acceptance"] is receipt["publication"] is False
    assert receipt["at"].endswith("+08:00")
    assert result["originals_preserved"] and result["other_owner_preserved"] and result["candidate_business_verified"]
    for key in ("message_metadata", "search_tokens", "assistant_created"):
        assert result["dry"][key] > 0 and result["first"][key] > 0
        assert result["repeat"][key] == 0
    assert result["state_before_sha256"] != result["state_after_sha256"]
    assert result["repeat"]["assistant_existing"] == 1
    assert "SYNTHETIC_B1_LEGACY_REPLY" not in output.read_text(encoding="utf-8")
    with psycopg.connect(proof_db.owner_dsn, row_factory=dict_row) as conn:
        replies = conn.execute(
            "SELECT data FROM mingjing_core.core_entities WHERE owner='primary' AND kind='message' "
            "AND data->>'role'='assistant'"
        ).fetchall()
        assert len(replies) == 1 and replies[0]["data"]["content"] == "SYNTHETIC_B1_LEGACY_REPLY"
        outbox = conn.execute("SELECT status,receipt FROM mingjing_core.delivery_outbox ORDER BY id").fetchall()
        assert outbox == [{"status": "sent", "receipt": "synthetic-receipt"}, {"status": "uncertain", "receipt": ""}]


@pytest.mark.parametrize("change", ["queue", "marker", "ledger"])
def test_unqualified_source_fails_without_partial_backfill(proof_db, monkeypatch, change):
    request = prepare(proof_db, monkeypatch)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        sql = {
            "queue": "UPDATE mingjing_core.core_runs SET status='queued' WHERE id='synthetic-run'",
            "marker": "UPDATE mingjing_core.core_runs SET result=NULL WHERE id='synthetic-run'",
            "ledger": "UPDATE mingjing_core.schema_migrations SET checksum='invalid' WHERE version=7",
        }
        conn.execute(sql[change])
    before = fingerprint(proof_db)
    with pytest.raises(ApplicationBlocked):
        run_worker(request)
    assert fingerprint(proof_db) == before


def test_restarting_whole_backfill_receipt_does_not_relabel_noop_as_first_success(proof_db, monkeypatch):
    request = prepare(proof_db, monkeypatch)
    run_worker(request)
    before = fingerprint(proof_db)
    with pytest.raises(ApplicationBlocked, match="APPLICATION_FIRST_APPLY_VACUOUS"):
        run_worker(replace(request, operation_id="b1-application-another"))
    assert fingerprint(proof_db) == before


def test_open_competing_session_rejected_without_backfill(proof_db, monkeypatch):
    request = prepare(proof_db, monkeypatch)
    before = fingerprint(proof_db)
    with psycopg.connect(proof_db.owner_dsn), pytest.raises(ApplicationBlocked, match="APPLICATION_OTHER_SESSIONS"):
        run_worker(request)
    assert fingerprint(proof_db) == before


def test_partial_metadata_and_token_writes_roll_back_when_reply_cannot_be_attributed(proof_db, monkeypatch):
    request = prepare(proof_db, monkeypatch)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        conn.execute(
            "UPDATE mingjing_core.core_runs SET request=jsonb_set(request,'{message}',"
            "'\"synthetic nonmatching original\"'::jsonb) WHERE id='synthetic-run'"
        )
    before = fingerprint(proof_db)
    with pytest.raises(ApplicationBlocked, match="APPLICATION_FIRST_APPLY_VACUOUS"):
        run_worker(request)
    assert fingerprint(proof_db) == before


def test_extra_primary_original_is_rejected_without_metadata_writes(proof_db, monkeypatch):
    request = prepare(proof_db, monkeypatch)
    with psycopg.connect(proof_db.owner_dsn) as conn:
        conn.execute(
            "INSERT INTO mingjing_core.core_entities(owner,kind,id,subject,data) VALUES "
            "('primary','message','unexpected-original','self','{\"content\":\"synthetic extra\"}')"
        )
    before = fingerprint(proof_db)
    with pytest.raises(ApplicationBlocked, match="SYNTHETIC_APPLICATION_ENTITIES_REQUIRED"):
        run_worker(request)
    assert fingerprint(proof_db) == before

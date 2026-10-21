"""Single case status acknowledgements need the model, mutation and exact own effect."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_pending_effects import pending_case_receipts
from mingjing_core.domain.contracts import CoreError
from mingjing_core.repositories.postgres import PostgresRepository

from .case_status_write_support import change_step, corrupt_private, prepare_write
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="write_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("status", ["paused", "closed"])
def test_proof_replay_after_pre_final_crash_keeps_one_saved_result(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    prepared = prepare_write(write_repo, monkeypatch, status)
    assert pending_case_receipts(write_repo, prepared.run) == ()
    envelope = prepared.finish()
    assert envelope["text"] == "事项状态已更新〔e1〕"
    assert len(envelope["receipts"]) == 1 and envelope["receipts"][0]["write_status"] == "saved"
    assert len([row for row in write_repo.list("alice", "message") if row.get("role") == "assistant"]) == 1


@pytest.mark.parametrize(
    "change",
    [
        "missing_model",
        "model_call",
        "step_started",
        "step_error",
        "step_no_finish",
        "step_receipt",
        "empty_receipt",
        "step_ok_false",
    ],
)
def test_completed_journal_and_original_normalized_model_call_are_required(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    with write_repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT seq,output FROM {} WHERE run_id=%s ORDER BY seq").format(
                write_repo.table("core_run_steps")
            ),
            (prepared.run["id"],),
        ).fetchall()
        if change == "missing_model":
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE run_id=%s AND seq=1").format(write_repo.table("core_run_steps")),
                (prepared.run["id"],),
            )
    if change == "model_call":
        rows[0]["output"]["assistant"]["tool_calls"][0]["arguments"]["changes"]["status"] = "paused"
        change_step(prepared, 1, "output", rows[0]["output"])
    elif change in {"step_receipt", "empty_receipt", "step_ok_false"}:
        if change == "step_receipt":
            rows[1]["output"]["receipt"]["id"] = "unrelated-case"
        elif change == "empty_receipt":
            rows[1]["output"]["receipt"] = {}
        else:
            rows[1]["output"]["ok"] = False
        change_step(prepared, 2, "output", rows[1]["output"])
    elif change in {"step_started", "step_error", "step_no_finish"}:
        field_name, value = {
            "step_started": ("status", "started"),
            "step_error": ("error_code", "synthetic_error"),
            "step_no_finish": ("finished_at", None),
        }[change]
        change_step(prepared, 2, field_name, value)
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize("change", ["initial_missing", "initial_hash", "ledger_missing", "ledger_hash"])
def test_protected_initial_alias_and_request_ledger_are_required(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    suffix = "agent_initial_context" if change.startswith("initial") else "agent_model_request:1"
    corrupt_private(prepared, suffix, remove=change.endswith("missing"))
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize(
    "change", ["missing_mutation", "mutation_fingerprint", "mutation_receipt", "missing_op", "op_time"]
)
def test_exact_mutation_and_effect_operation_cannot_be_replaced_by_any_saved_receipt(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    operation = f"run:{prepared.run['id']}:e0:s2"
    with write_repo.transaction("alice") as connection:
        if change.startswith("missing_"):
            mutation = change == "missing_mutation"
            table, field_name, key = (
                ("core_mutation_requests", "request_key", operation)
                if mutation
                else ("core_operations", "operation_id", operation + ":case")
            )
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner='alice' AND {}=%s").format(
                    write_repo.table(table), sql.Identifier(field_name)
                ),
                (key,),
            )
        elif change.startswith("mutation_"):
            field_name = "fingerprint" if change == "mutation_fingerprint" else "receipt"
            value = (
                "0" * 64
                if field_name == "fingerprint"
                else Jsonb({"write_status": "saved", "kind": "case", "id": "other", "revision": 2})
            )
            connection.execute(
                sql.SQL("UPDATE {} SET {}=%s WHERE owner='alice' AND request_key=%s").format(
                    write_repo.table("core_mutation_requests"), sql.Identifier(field_name)
                ),
                (value, operation),
            )
        else:
            connection.execute(
                sql.SQL("UPDATE {} SET created_at=created_at-interval '1 second' WHERE operation_id=%s").format(
                    write_repo.table("core_operations")
                ),
                (operation + ":case",),
            )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("revision", 99),
        ("revision", True),
        ("id", "foreign"),
        ("kind", "note"),
        ("basis", "invented"),
        ("basis", "case_index"),
    ],
)
def test_alias_self_report_is_not_the_initial_selected_case_identity(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, field_name: str, value: Any
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    prepared.inputs["alias_map"]["e1"][field_name] = value
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()


@pytest.mark.parametrize(
    "change", ["old_epoch", "lease", "unselected", "external_revision", "revoked_case", "revoked_source", "source_refs"]
)
def test_current_scope_lease_revision_and_source_cannot_be_overridden_by_own_receipt(
    write_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    prepared = prepare_write(write_repo, monkeypatch)
    if change == "external_revision":
        row = write_repo.get("alice", "case", prepared.case["id"])
        write_repo.update("alice", "case", row["id"], {"title": "外部真实新修订"}, expected_revision=row["revision"])
    else:
        with write_repo.transaction("alice") as connection:
            if change.startswith("revoked_"):
                kind, ident = (
                    ("case", prepared.case["id"])
                    if change == "revoked_case"
                    else ("message", prepared.run["request"]["source_message_id"])
                )
                write_repo.revoke(connection, "alice", kind, ident, "synthetic_withdrawal")
            elif change == "source_refs":
                connection.execute(
                    sql.SQL(
                        "UPDATE {} SET data=jsonb_set(data,'{{source_refs}}','[]'::jsonb) WHERE kind='case' AND id=%s"
                    ).format(write_repo.table("core_entities")),
                    (prepared.case["id"],),
                )
            else:
                changes = {
                    "old_epoch": "retry_epoch=retry_epoch+1",
                    "lease": "lease_until=now()-interval '1 second'",
                    "unselected": "request=jsonb_set(request,'{{case_ids}}','[]'::jsonb)",
                }
                connection.execute(
                    sql.SQL("UPDATE {} SET " + changes[change] + " WHERE id=%s").format(write_repo.table("core_runs")),
                    (prepared.run["id"],),
                )
    with pytest.raises(CoreError):
        prepared.finish()
    prepared.unpublished()

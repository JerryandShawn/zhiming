"""No event is manufactured from a forged acknowledgement, authority or receipt."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.loop_batch import ToolBatch
from mingjing_core.application.agent_tools_contracts import ToolContext
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock
from tests.v4.agent.test_loop_cycle_support import cycle_repo as source_repo_fixture
from tests.v4.streaming_integration.memory_receipt_support import ReceiptCase, make_case
from tests.v4.streaming_integration.test_event_notify_pg import listener, notified


@pytest.fixture(name="receipt_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def count_events(case: ReceiptCase) -> int:
    with case.repo.pool.connection() as connection:
        return connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s AND kind='memory_receipt'").format(
                case.repo.table("core_run_events")
            ),
            ("alice", case.cycle.run["id"]),
        ).fetchone()["n"]


def alter(case: ReceiptCase, table: str, assignment: Any, *, tool: bool = False) -> None:
    step, repo = case.prepared.step, case.repo
    if tool:
        predicate, values = (
            "owner=%s AND run_id=%s AND epoch=%s AND seq=%s",
            ("alice", step.run_id, step.epoch, step.seq),
        )
    else:
        predicate, values = (
            "owner=%s AND operation=%s AND request_key=%s",
            ("alice", "agent_" + step.name, step.operation_id),
        )
    with repo.transaction("alice") as connection:
        connection.execute(sql.SQL("UPDATE {} SET {} WHERE " + predicate).format(repo.table(table), assignment), values)


@pytest.mark.parametrize(
    "change",
    [
        "started",
        "finished",
        "output",
        "error",
        "mutation_missing",
        "mutation_operation",
        "mutation_key",
        "mutation_fingerprint",
        "mutation_receipt",
    ],
)
def test_exact_completed_step_and_mutation_proof_are_required(receipt_repo: PostgresRepository, change: str) -> None:
    case = make_case(receipt_repo)
    step_changes = {
        "started": "status='started',output=NULL,finished_at=NULL",
        "finished": "finished_at=NULL",
        "output": "output='{}'::jsonb",
        "error": "error_code='SYNTHETIC_INVALID'",
    }
    mutation_changes = {
        "mutation_operation": "operation='agent_note_write'",
        "mutation_key": "request_key=request_key||':other'",
        "mutation_fingerprint": "fingerprint=repeat('f',64)",
        "mutation_receipt": "receipt=jsonb_set(receipt,'{revision}','999'::jsonb)",
    }
    if change == "mutation_missing":
        with case.repo.transaction("alice") as connection:
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                    case.repo.table("core_mutation_requests")
                ),
                ("alice", "agent_memory_write", case.prepared.step.operation_id),
            )
    elif change in step_changes:
        alter(case, "core_run_steps", sql.SQL(step_changes[change]), tool=True)
    else:
        alter(case, "core_mutation_requests", sql.SQL(mutation_changes[change]))
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0 and case.observed == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner", "bob"),
        ("subject", "synthetic_other_subject"),
        ("epoch", 1),
        ("seq", 99),
        ("lease_token", "synthetic_other_lease"),
        ("thread_id", "life:other"),
        ("input_fp", "b" * 64),
        ("source_ids", ("synthetic_outside_source",)),
        ("incognito", True),
        ("crisis", True),
    ],
)
def test_context_cannot_expand_real_tool_or_source_authority(
    receipt_repo: PostgresRepository, field: str, value: Any
) -> None:
    case = make_case(receipt_repo)
    ctx: ToolContext = replace(case.prepared.context, **{field: value})
    case.prepared = replace(case.prepared, context=ctx)
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0 and case.observed == []


@pytest.mark.parametrize(
    "clause",
    [
        "retry_epoch=retry_epoch+1",
        "lease_token='synthetic_other_lease'",
        "lease_until=now()-interval '1 second'",
        "cancel_requested_at=now()",
        "expired_deadline",
    ],
)
def test_real_run_epoch_lease_cancel_and_deadline_remain_fenced(receipt_repo: PostgresRepository, clause: str) -> None:
    case = make_case(receipt_repo)
    assignment = (
        sql.SQL("deadline_at={}").format(sql.Literal(get_clock().now() - timedelta(seconds=1)))
        if clause == "expired_deadline"
        else sql.SQL(clause)
    )
    with case.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE owner=%s AND id=%s").format(case.repo.table("core_runs"), assignment),
            ("alice", case.cycle.run["id"]),
        )
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0


@pytest.mark.parametrize("change", ["arguments", "source_version", "source_revoke", "span_revoke", "entity_revision"])
def test_original_input_and_current_authorized_lineage_are_required(
    receipt_repo: PostgresRepository, change: str
) -> None:
    case = make_case(receipt_repo)
    source = case.cycle.run["request"]["source_message_id"]
    if change == "arguments":
        case.prepared = replace(case.prepared, call=replace(case.prepared.call, arguments={"summary": "other"}))
    elif change == "source_version":
        ctx = case.prepared.context
        versions = dict(ctx.source_versions, **{"message:" + source: 999})
        case.prepared = replace(case.prepared, context=replace(ctx, source_versions=versions))
    elif change == "entity_revision":
        row = case.repo.get("alice", "fact", case.result.receipt["fact_id"])
        case.repo.update("alice", "fact", row["id"], {"summary": "外部实际修订"}, expected_revision=row["revision"])
    else:
        with case.repo.transaction("alice") as connection:
            case.repo.revoke(
                connection,
                "alice",
                "message" if change == "source_revoke" else "source_span",
                source if change == "source_revoke" else "synthetic_span",
                "stopped",
                {"message_id": source, "start": 0, "end": len(case.cycle.run["request"]["message"])},
            )
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0


def test_proposal_rejected_after_effect_is_not_projected_as_pending(receipt_repo: PostgresRepository) -> None:
    case = make_case(receipt_repo, text="我确诊了合成焦虑症")
    row = case.repo.get("alice", "proposal", case.result.receipt["id"])
    case.repo.update("alice", "proposal", row["id"], {"status": "rejected"}, expected_revision=row["revision"])
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0


def test_uncommitted_outer_transaction_is_rejected_before_ack_or_callback(receipt_repo: PostgresRepository) -> None:
    case = make_case(receipt_repo, acknowledge=False)
    case.cycle.memory_receipts = case.hook
    with case.repo.transaction("alice"), pytest.raises(EvidenceError, match="已有外层事务"):
        ToolBatch(case.cycle).accept(case.prepared, case.result)
    with case.repo.pool.connection() as connection:
        row = connection.execute(
            sql.SQL("SELECT status FROM {} WHERE owner=%s AND run_id=%s AND epoch=0 AND seq=1").format(
                case.repo.table("core_run_steps")
            ),
            ("alice", case.cycle.run["id"]),
        ).fetchone()
    assert row["status"] == "started" and count_events(case) == 0 and case.observed == []


def test_record_requires_an_existing_ack_transaction_and_dispatch_requires_it_to_end(
    receipt_repo: PostgresRepository,
) -> None:
    case = make_case(receipt_repo)
    with pytest.raises(EvidenceError, match="同一事务"):
        case.hook.record(
            case.prepared.step, case.result, arguments=case.prepared.call.arguments, context=case.prepared.context
        )
    with case.repo.transaction("alice"):
        event = case.record()
        with pytest.raises(EvidenceError, match="已有外层事务"):
            case.hook.dispatch(event)
    assert case.observed == []
    case.hook.dispatch(event)
    assert len(case.observed) == count_events(case) == 1
    assert case.record() is None and count_events(case) == 1


def test_forged_result_and_matching_journal_cannot_replace_real_mutation_receipt(
    receipt_repo: PostgresRepository,
) -> None:
    case = make_case(receipt_repo)
    receipt = dict(case.result.receipt, id="synthetic_forged_fact", fact_id="synthetic_forged_fact")
    case.result = case.result.model_copy(update={"receipt": receipt})
    alter(case, "core_run_steps", sql.SQL("output={}").format(sql.Literal(Jsonb(case.result.model_dump()))), tool=True)
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0


def test_real_correction_keeps_stale_invalidation_instead_of_forging_an_ack(receipt_repo: PostgresRepository) -> None:
    repo, memory = receipt_repo, MemoryService(receipt_repo)
    source = memory.receive("alice", content="我喜欢早上阅读", source_id="synthetic_old_fact", at=get_clock().now())
    old = memory.save_fact("alice", "self", source["id"], source["content"], "preference")

    def arguments(run: dict) -> dict:
        return {
            "fact_id": old["id"],
            "expected_revision": old["revision"],
            "message_id": run["request"]["source_message_id"],
            "quote": run["request"]["message"],
            "summary": "合成更正",
        }

    case = make_case(
        repo,
        text="更正：我喜欢早上阅读是记错了，我现在喜欢晚上阅读",
        name="memory_update",
        arguments=arguments,
        acknowledge=False,
    )
    assert case.result.ok and repo.fetch_run("alice", case.cycle.run["id"])["status"] == "stale"
    case.cycle.memory_receipts = case.hook
    with pytest.raises(CoreError):
        ToolBatch(case.cycle).accept(case.prepared, case.result)
    assert count_events(case) == 0 and case.observed == []
    assert repo.get("alice", "fact", old["id"], include_deleted=True)["status"] == "superseded"


def test_actual_forget_preserves_revocation_instead_of_acknowledging_the_old_run(
    receipt_repo: PostgresRepository,
) -> None:
    repo, memory = receipt_repo, MemoryService(receipt_repo)
    source = memory.receive("alice", content="我喜欢合成夜班", source_id="synthetic_forget_old", at=get_clock().now())
    old = memory.save_fact("alice", "self", source["id"], source["content"], "preference")

    def arguments(run: dict) -> dict:
        return {"fact_id": old["id"], "message_id": run["request"]["source_message_id"]}

    case = make_case(repo, text="请忘记我喜欢合成夜班", name="memory_forget", arguments=arguments, acknowledge=False)
    assert case.result.ok and repo.fetch_run("alice", case.cycle.run["id"])["status"] == "revoked"
    case.cycle.memory_receipts = case.hook
    with pytest.raises(CoreError):
        ToolBatch(case.cycle).accept(case.prepared, case.result)
    assert count_events(case) == 0 and case.observed == []
    assert repo.get("alice", "fact", old["id"], include_deleted=True)["status"] == "deleted"


@pytest.mark.parametrize("scope", ["owner", "subject", "source"])
def test_matching_forged_receipt_and_ack_do_not_authorize_an_unrelated_real_entity(
    receipt_repo: PostgresRepository, scope: str
) -> None:
    case = make_case(receipt_repo)
    repo, memory = receipt_repo, MemoryService(receipt_repo)
    owner, subject = ("bob" if scope == "owner" else "alice"), ("other" if scope == "subject" else "self")
    repo.ensure_owner(owner)
    if subject != "self":
        repo.create_subject(owner, subject, "合成另一人物")
    text = "请记住我喜欢另一种合成班次"
    source = memory.receive(owner, subject, content=text, source_id="synthetic_other_scope", at=get_clock().now())
    fact = memory.save_fact(owner, subject, source["id"], text, "preference")
    assert fact["write_status"] == "saved"
    receipt = dict(case.result.receipt, id=fact["id"], fact_id=fact["id"], revision=fact["revision"])
    case.result = case.result.model_copy(update={"receipt": receipt})
    alter(case, "core_run_steps", sql.SQL("output={}").format(sql.Literal(Jsonb(case.result.model_dump()))), tool=True)
    alter(case, "core_mutation_requests", sql.SQL("receipt={}").format(sql.Literal(Jsonb(receipt))))
    with pytest.raises(CoreError):
        case.record()
    assert count_events(case) == 0


def test_real_pg_notify_rolls_back_and_replay_has_no_new_seq_or_notification(receipt_repo: PostgresRepository) -> None:
    case = make_case(receipt_repo)
    with listener(case.repo) as channel:
        with pytest.raises(SystemExit), case.repo.transaction("alice"):
            case.record()
            assert notified(channel, case.cycle.run) == []
            raise SystemExit("synthetic outer rollback")
        assert count_events(case) == 0 and notified(channel, case.cycle.run) == []
        event = case.record()
        assert event is not None and notified(channel, case.cycle.run) == [f"{case.cycle.run['id']}:1"]
        assert case.record() is None and notified(channel, case.cycle.run) == []
    case.hook.dispatch(event)
    assert count_events(case) == len(case.observed) == 1


def test_callback_failure_cannot_undo_committed_memory_or_event(receipt_repo: PostgresRepository) -> None:
    case = make_case(receipt_repo)

    def disconnected(event: dict) -> None:
        raise ConnectionError("synthetic disconnected callback")

    case.hook.events.callback = disconnected
    event = case.record()
    case.hook.dispatch(event)
    assert count_events(case) == 1 and len(case.repo.list("alice", "fact")) == 1


def test_note_does_not_masquerade_as_a_fact_receipt(receipt_repo: PostgresRepository) -> None:
    case = make_case(
        receipt_repo,
        name="note_write",
        arguments=lambda run: {"summary": "合成推断", "source_ids": [run["request"]["source_message_id"]]},
    )
    assert case.result.ok and len(receipt_repo.list("alice", "note")) == 1
    assert case.record() is None and count_events(case) == 0


def test_profile_change_request_has_a_real_pending_proposal_and_no_undo_token(receipt_repo: PostgresRepository) -> None:
    case = make_case(
        receipt_repo,
        text="请更正我的出生时间：2000-01-01 10:00",
        name="profile_update_request",
        arguments=lambda run: {
            "message_id": run["request"]["source_message_id"],
            "quote": run["request"]["message"],
            "fields": ["birth.solar_datetime"],
        },
    )
    event = case.record()
    assert event is not None and event["data"]["proposal_id"] == case.result.receipt["id"]
    assert event["data"]["write_status"] == "pending_confirm" and event["data"]["sensitive"] is True
    assert "undo_token" not in event["data"] and receipt_repo.list("alice", "fact") == []

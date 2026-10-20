"""Second-batch application effects use the same authoritative run and source."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.toolkit import ToolContext, ToolResult
from mingjing_core.agent.tools.interaction_parameters import (
    AskUser,
    CaseAddEvent,
    CaseList,
    CaseUpdate,
    PresentOptions,
    ScheduleFollowup,
    SetReminder,
)
from mingjing_core.application.agent_tools_cases import execute_case
from mingjing_core.application.agent_tools_clarification import apply_clarification_answer, execute_clarification
from mingjing_core.application.agent_tools_contracts import tool_input_fingerprint
from mingjing_core.application.agent_tools_followups import execute_schedule
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import SAID_AT, Harness, Parser, setup
from .test_toolkit_pg import tool_repo as source_tool_repo

PARAMETERS = {
    "case_list": CaseList,
    "case_update": CaseUpdate,
    "case_add_event": CaseAddEvent,
    "ask_user": AskUser,
    "present_options": PresentOptions,
    "schedule_followup": ScheduleFollowup,
    "set_reminder": SetReminder,
}
QUESTION = {
    "question": "你最在意什么？",
    "options": ["稳定", "成长"],
    "allow_free_text": True,
    "why": "选择影响建议",
    "slot": "最在意因素",
    "changes_conclusion": "会改变工作比较的顺序",
}


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_tool_repo.__wrapped__(p2_repo, monkeypatch)


def call(h: Harness, name: str, args: dict[str, Any], **flags: Any) -> tuple[ToolResult, ToolContext]:
    args = PARAMETERS[name].model_validate(args).model_dump()
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=tool_input_fingerprint(name, args))
    flags.setdefault("case_ids", tuple(h.run["request"].get("case_ids", [])))
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],), **flags)
    execute = (
        execute_case
        if name.startswith("case_")
        else execute_schedule
        if name in {"schedule_followup", "set_reminder"}
        else execute_clarification
    )
    return execute(h.service, name, args, ctx), ctx


def case(h: Harness) -> dict[str, Any]:
    row = MemoryService(h.repo).create_case("alice", "self", "合成事项", operation_id="synthetic-case")
    MemoryService(h.repo).receive(
        "alice", content=h.source["content"], source_id=h.source["source_id"], case_ids=[row["id"]], at=SAID_AT
    )
    with h.repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET request=jsonb_set(request,'{{case_ids}}',%s) WHERE id=%s").format(
                h.repo.table("core_runs")
            ),
            (Jsonb([row["id"]]), h.run["id"]),
        )
    h.run = h.repo.fetch_run("alice", h.run["id"])
    return row


def test_ask_replay_preserves_context_guard_and_only_one_question_per_run(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "帮我比较合成选项")
    tool_repo.put("alice", "thread", "life:self", {"context_guard": {"large_streak": 2}}, expected_revision=0)
    asked, ctx = call(h, "ask_user", QUESTION)
    assert asked.ok and asked.ends_turn and asked.data["asked"]["slot"] == "最在意因素"
    revision = tool_repo.get_revision("alice")
    replay = execute_clarification(h.service, "ask_user", AskUser(**QUESTION).model_dump(), ctx)
    assert replay == asked and tool_repo.get_revision("alice") == revision
    row = tool_repo.get("alice", "thread", "life:self")
    assert row["context_guard"] == {"large_streak": 2} and row["clarify_slots"][0]["asked_count"] == 1
    again, _ = call(h, "ask_user", dict(QUESTION, slot="工作地点"))
    assert not again.ends_turn and again.data["error"] == "question_already_asked"


@pytest.mark.parametrize("answer,status", [("我更在意稳定", "filled"), ("不知道", "declined")])
def test_real_next_source_updates_slot_once_and_preserves_other_thread_fields(
    tool_repo: PostgresRepository,
    answer: str,
    status: str,
) -> None:
    h = setup(tool_repo, "帮我比较合成选项")
    call(h, "ask_user", QUESTION)
    assert apply_clarification_answer(tool_repo, h.run, h.service.clock) == 0
    h.finish()
    reply = setup(tool_repo, answer)
    assert apply_clarification_answer(tool_repo, reply.run, reply.service.clock) == 1
    row = tool_repo.get("alice", "thread", "life:self")
    assert row["clarify_slots"][0]["status"] == status
    assert row["clarify_slots"][0]["answer_message_id"] == reply.source["id"]
    revision = tool_repo.get_revision("alice")
    assert apply_clarification_answer(tool_repo, reply.run, reply.service.clock) == 0
    assert tool_repo.get_revision("alice") == revision
    result, _ = call(reply, "ask_user", QUESTION)
    assert not result.ends_turn and result.data["error"] == (
        "slot_declined" if status == "declined" else "slot_already_filled"
    )


def test_third_same_slot_refused_then_expiry_starts_fresh(tool_repo: PostgresRepository) -> None:
    for count in range(3):
        h = setup(tool_repo, "合成讨论" + str(count))
        result, _ = call(h, "ask_user", QUESTION)
        assert result.ends_turn == (count < 2)
        h.finish()
    assert result.data["error"] == "slot_exhausted"
    h = setup(tool_repo, "过期后再讨论")
    h.service.clock = FrozenClock(SAID_AT + timedelta(days=8))
    result, _ = call(h, "ask_user", QUESTION)
    assert result.ok and tool_repo.get("alice", "thread", "life:self")["clarify_slots"][0]["asked_count"] == 1


@pytest.mark.parametrize("change", ["cancel_requested_at=now()", "retry_epoch=1", "lease_token='wrong'"])
def test_answer_application_requires_current_lease_epoch_and_live_source(
    tool_repo: PostgresRepository,
    change: str,
) -> None:
    h = setup(tool_repo, "帮我比较合成选项")
    call(h, "ask_user", QUESTION)
    h.finish()
    reply = setup(tool_repo, "我不想回答")
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE id=%s").format(tool_repo.table("core_runs"), sql.SQL(change)),
            (reply.run["id"],),
        )
    before = tool_repo.get_revision("alice")
    with pytest.raises(LeaseConflict):
        apply_clarification_answer(tool_repo, reply.run, reply.service.clock)
    assert tool_repo.get_revision("alice") == before


def test_present_options_is_read_only_and_separates_all_decision_fields(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "比较两个合成选择")
    option = {
        "title": "合成A",
        "benefit": "收益",
        "cost": "成本",
        "risk": "风险",
        "reversibility": "可逆",
        "first_step": "先核实条件",
    }
    before = tool_repo.get_revision("alice")
    result, _ = call(h, "present_options", {"options": [option, dict(option, title="合成B")]})
    assert result.ok and len(result.data["options"]) == 2 and not result.ends_turn
    assert tool_repo.get_revision("alice") == before


def test_case_updates_and_events_preserve_originals_replay_and_revision(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "事项改为完成合成报告")
    row = case(h)
    args = {
        "id": row["id"],
        "changes": {"goal": "完成合成报告"},
        "expected_revision": row["revision"],
        "message_id": h.source["id"],
        "quote": h.source["content"],
    }
    result, ctx = call(h, "case_update", args, case_ids=(row["id"],))
    assert result.ok and tool_repo.get("alice", "case", row["id"])["state"]["goal"] == "完成合成报告"
    current = tool_repo.get("alice", "case", row["id"])
    assert current["field_source_refs"]["goal"][0]["quote"] == "完成合成报告"
    assert current["field_source_refs"]["title"] == []
    replay = execute_case(h.service, "case_update", CaseUpdate(**args).model_dump(), ctx)
    assert replay.receipt == result.receipt
    event = {
        "id": row["id"],
        "kind": "progress",
        "content": h.source["content"],
        "message_id": h.source["id"],
        "expected_revision": result.receipt["revision"],
    }
    result, _ = call(h, "case_add_event", event, case_ids=(row["id"],))
    feedback = tool_repo.get("alice", "feedback", result.receipt["id"])
    assert feedback["source_refs"][0]["quote"] == h.source["content"]
    assert len(tool_repo.list("alice", "message")) == 1
    index, _ = call(h, "case_list", {})
    assert index.data["cases"][0]["id"] == row["id"]


def test_case_rejects_invented_content_unselected_scope_and_stale_revision(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "合成当前原话")
    row = case(h)
    args = {
        "id": row["id"],
        "changes": {"goal": "模型杜撰目标"},
        "expected_revision": row["revision"],
        "message_id": h.source["id"],
        "quote": h.source["content"],
    }
    with pytest.raises(ScopeError):
        call(h, "case_update", args, case_ids=())
    with pytest.raises(EvidenceError):
        call(h, "case_update", args, case_ids=(row["id"],))
    with pytest.raises(RevisionConflict):
        call(h, "case_update", dict(args, expected_revision=2), case_ids=(row["id"],))
    assert tool_repo.get("alice", "case", row["id"])["revision"] == row["revision"]


def schedule_args(h: Harness, *, reminder: bool = False) -> dict[str, Any]:
    common = {"message_id": h.source["id"], "quote": h.source["content"], "due_at": "2026-10-21T20:00:00+08:00"}
    return dict(common, text="开会") if reminder else dict(common, topic="面试", reason="事件后跟进")


@pytest.mark.parametrize(
    "name,text",
    [
        ("schedule_followup", "我在2026-10-21参加面试"),
        ("set_reminder", "提醒我2026-10-21 20:00开会"),
    ],
)
def test_schedules_create_only_local_due_rows_and_replay_once(
    tool_repo: PostgresRepository,
    name: str,
    text: str,
) -> None:
    h = setup(tool_repo, text)
    args = schedule_args(h, reminder=name == "set_reminder")
    result, ctx = call(h, name, args)
    assert result.ok
    row = tool_repo.get("alice", result.receipt["kind"], result.receipt["id"])
    assert row["due_at"] == "2026-10-21T12:00:00+00:00" and row["due_ms"] > 0
    assert row["source_refs"][0]["quote"] == text and row["thread_id"] == "life:self"
    revision = tool_repo.get_revision("alice")
    replay = execute_schedule(h.service, name, PARAMETERS[name](**args).model_dump(), ctx)
    assert replay.receipt == result.receipt and tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(tool_repo.table("delivery_outbox"))
            ).fetchone()["n"]
            == 0
        )


def test_reminder_requires_explicit_request_and_confirmed_time(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我2026-10-21 20:00开会")
    result, _ = call(h, "set_reminder", schedule_args(h, reminder=True))
    assert result.receipt["code"] == "explicit_reminder_required"
    h.finish()
    h = setup(tool_repo, "提醒我2026-10-21开会")
    result, _ = call(h, "set_reminder", schedule_args(h, reminder=True))
    assert result.receipt["code"] == "reminder_text_or_time_unconfirmed"
    assert tool_repo.list("alice", "reminder") == []


def test_relative_followup_needs_parser_or_uses_source_clock(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我下周三参加面试")
    result, _ = call(h, "schedule_followup", schedule_args(h))
    assert result.receipt["code"] == "date_parser_unavailable"
    h.finish()
    h = setup(tool_repo, "我下周三参加面试", parser=Parser())
    result, _ = call(h, "schedule_followup", schedule_args(h))
    assert result.ok
    row = tool_repo.get("alice", "followup", result.receipt["id"])
    assert row["event_at"] == "2026-10-21" and row["original_expression"] == "下周三"


def test_private_and_invalid_authority_cannot_schedule(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "我在2026-10-21参加面试")
    args = schedule_args(h)
    result, ctx = call(h, "schedule_followup", args, incognito=True)
    assert not result.ok
    with pytest.raises(LeaseConflict):
        execute_schedule(
            h.service,
            "schedule_followup",
            ScheduleFollowup(**args).model_dump(),
            replace(ctx, incognito=False, lease_token="wrong"),
        )
    assert tool_repo.list("alice", "followup") == []


@pytest.mark.parametrize("name", ["ask_user", "schedule_followup"])
def test_changed_arguments_before_first_effect_cannot_use_another_step_fingerprint(
    tool_repo: PostgresRepository,
    name: str,
) -> None:
    h = setup(tool_repo, "我2026-10-21参加面试")
    intended = PARAMETERS[name](**(QUESTION if name == "ask_user" else schedule_args(h))).model_dump()
    step = h.journal.next_or_replay(h.run, kind="tool", name=name, input_fp=tool_input_fingerprint(name, intended))
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))
    changed = (
        dict(intended, question="篡改问题")
        if name == "ask_user"
        else dict(intended, due_at="2026-10-22T20:00:00+08:00")
    )
    execute = execute_clarification if name == "ask_user" else execute_schedule
    before = tool_repo.get_revision("alice")
    with pytest.raises(ScopeError):
        execute(h.service, name, changed, ctx)
    assert tool_repo.get_revision("alice") == before
    assert tool_repo.list("alice", "thread") == [] and tool_repo.list("alice", "followup") == []


def test_proactive_optout_does_not_disable_explicit_reminders(tool_repo: PostgresRepository) -> None:
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=jsonb_set(settings,'{{proactive_followups_enabled}}','false')").format(
                tool_repo.table("core_owners")
            )
        )
    h = setup(tool_repo, "我2026-10-21参加面试")
    result, _ = call(h, "schedule_followup", schedule_args(h))
    assert result.receipt["code"] == "proactive_disabled"
    h.finish()
    h = setup(tool_repo, "提醒我2026-10-21 20:00开会")
    result, _ = call(h, "set_reminder", schedule_args(h, reminder=True))
    assert result.ok and len(tool_repo.list("alice", "reminder")) == 1

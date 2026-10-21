"""Context snapshots use real PostgreSQL, original writers and revoked spans."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_types import BudgetPolicy, ContextInputError, InputMeterUnverified
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.models.port import ChatMessage, ToolCall
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

if TYPE_CHECKING:
    from mingjing_core.agent.context_types import ContextBuild
    from mingjing_core.repositories.postgres import PostgresRepository


@pytest.fixture(name="memory")
def context_memory_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[MemoryService]:
    def reject_http(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("离线上下文测试禁止HTTP请求")

    monkeypatch.setattr(httpx.Client, "send", reject_http)
    old = get_clock()
    set_clock(FrozenClock(datetime(2026, 10, 17, 2, 30, tzinfo=UTC)))
    try:
        yield MemoryService(p2_repo)
    finally:
        set_clock(old)


def receive(memory: MemoryService, text: str, ident: str = "current", **kwargs: Any) -> dict[str, Any]:
    return memory.receive("alice", content=text, source_id=ident, channel="synthetic", **kwargs)


def build(memory: MemoryService, source: dict[str, Any], **kwargs: Any) -> ContextBuild:
    return ContextEngine(memory, "合成测试人格：只根据有效来源回答。", clock=get_clock()).build(
        "alice", source["id"], **kwargs
    )


def text_of(result: ContextBuild) -> str:
    return "\n".join(str(message.content) for message in result.messages)


def test_real_fact_writer_and_current_source_are_used(memory: MemoryService) -> None:
    original = receive(memory, "请记住，我不能上夜班", "constraint")
    fact = memory.save_fact("alice", "self", original["id"], "我不能上夜班", "constraint")
    current = receive(memory, "现在适合考虑哪种工作？")
    result = build(memory, current)
    assert "我不能上夜班" in text_of(result)
    assert result.messages[-1].content == current["content"]
    assert result.injected_versions["fact:" + fact["id"]] == fact["revision"]
    assert result.meter.actual_input_tokens is None
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(result.budget)


def test_partial_withdrawal_masks_history_and_removes_the_fact(memory: MemoryService) -> None:
    original = receive(memory, "我不能上夜班。准备考研", "old")
    fact = memory.save_fact("alice", "self", original["id"], "我不能上夜班", "constraint")
    current = receive(memory, "还记得安排吗")
    assert "我不能上夜班" in text_of(build(memory, current))
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    result = build(memory, current, query="考研")
    assert "我不能上夜班" not in text_of(result)
    assert "准备考研" in text_of(result)


def test_duplicate_quote_cannot_authorize_a_revoked_original_span(memory: MemoryService) -> None:
    original = receive(memory, "我不能上夜班。后来又说：我不能上夜班", "duplicate")
    fact = memory.save_fact("alice", "self", original["id"], "我不能上夜班", "constraint")
    # An active row beside a revoked source span is a deliberate hostile ledger fixture.
    with memory.repo.transaction("alice") as connection:
        memory.repo.revoke(
            connection,
            "alice",
            "source_span",
            "hostile-span",
            "deleted",
            {"message_id": original["id"], "start": 0, "end": 6},
        )
    result = build(memory, receive(memory, "给我建议"))
    assert all(value["id"] != fact["id"] for value in result.alias_map.values())
    assert "<画像>" not in text_of(result)
    assert "后来又说：我不能上夜班" in text_of(result)


def test_stale_source_revision_does_not_inject_an_active_fact(memory: MemoryService) -> None:
    original = receive(memory, "我不能上夜班", "stale")
    memory.save_fact("alice", "self", original["id"], original["content"], "constraint")
    memory.repo.update("alice", "message", original["id"], {"synthetic_metadata": True}, expected_revision=1)
    result = build(memory, receive(memory, "考虑工作安排"))
    assert "<画像>" not in text_of(result)


def test_other_owner_and_other_subject_are_not_visible(memory: MemoryService) -> None:
    memory.repo.create_subject("alice", "other", "已授权的另一个人物")
    memory.receive("bob", content="别人私密的考研安排", source_id="bob", channel="synthetic")
    memory.receive("alice", "other", content="另一个人物考研安排", source_id="other", channel="synthetic")
    result = build(memory, receive(memory, "考研"), query="考研")
    assert "私密" not in text_of(result) and "另一个人物" not in text_of(result)
    bob = memory.receive("bob", content="给我建议", source_id="bob-current", channel="synthetic")
    with pytest.raises(ScopeError):
        build(memory, bob)


def test_unselected_case_fts_hits_do_not_leak(memory: MemoryService) -> None:
    case = memory.create_case("alice", "self", "不选择的事项")
    receive(memory, "考研秘密计划", "secret", case_ids=[case["id"]])
    current = receive(memory, "考研")
    assert "秘密计划" not in text_of(build(memory, current, query="考研"))
    selected = build(memory, current, case_ids=(case["id"],), query="考研")
    assert "考研秘密计划" in text_of(selected)


@pytest.mark.parametrize("thread", ["life:other", "incognito:unimplemented", "unknown"])
def test_unsupported_threads_fail_closed(memory: MemoryService, thread: str) -> None:
    with pytest.raises(ContextInputError):
        build(memory, receive(memory, "当前问题"), thread_id=thread)


def test_bounded_fact_catalog_overflow_does_not_silently_drop_constraints(memory: MemoryService) -> None:
    for index in range(2):
        source = receive(memory, f"我不能上夜班{index}", str(index))
        memory.save_fact("alice", "self", source["id"], source["content"], "constraint")
    current = receive(memory, "给建议")
    engine = ContextEngine(memory, "合成系统", policy=BudgetPolicy(fact_limit=1))
    with pytest.raises(ContextInputError) as error:
        engine.build("alice", current["id"])
    assert error.value.code == "context_source_catalog_overflow"


def test_revocation_catalog_overflow_is_explicit(memory: MemoryService) -> None:
    with memory.repo.transaction("alice") as connection:
        for index in range(2):
            memory.repo.revoke(connection, "alice", "message", str(index), "deleted")
    engine = ContextEngine(memory, "合成系统", policy=BudgetPolicy(revocation_limit=1))
    with pytest.raises(ContextInputError) as error:
        engine.build("alice", receive(memory, "当前问题")["id"])
    assert error.value.code == "context_source_catalog_overflow"


def test_same_cycle_full_reasoning_is_retained_but_new_turn_has_none(memory: MemoryService) -> None:
    source = receive(memory, "当前问题")
    cycle = (
        ChatMessage(
            "assistant",
            "查一下",
            [ToolCall("a", "search", {})],
            reasoning="private",
            reasoning_signature="sig",
            tool_cycle="run:e0",
        ),
        ChatMessage("tool", '{"ok":true}', tool_call_id="a", tool_cycle="run:e0"),
    )
    first = build(memory, source, current_epoch_messages=cycle)
    assert first.messages[-2].reasoning == "private" and first.messages[-2].reasoning_signature == "sig"
    second = build(memory, receive(memory, "新一轮", "next"))
    assert all(not item.reasoning and not item.reasoning_signature for item in second.messages)
    with pytest.raises(ContextInputError):
        build(memory, source, current_epoch_messages=(ChatMessage("user", "unverified"),))
    third = receive(memory, "第三轮", "third")
    with pytest.raises(ContextInputError):
        build(memory, third, current_epoch_messages=(cycle[0], replace(cycle[1], tool_cycle="run:e1")))
    with pytest.raises(ContextInputError):
        build(memory, third, current_epoch_messages=(ChatMessage("assistant", "没有tag"),))


def test_assistant_history_keeps_a_real_alias_and_can_be_found_far_away(memory: MemoryService) -> None:
    receive(memory, "旧轮问题", "old")
    assistant = memory.record_assistant_message(
        "alice", "self", "life:self", "考研方案B先准备材料", run_id="old-run", channel="web"
    )
    result = build(memory, receive(memory, "考研"), query="考研")
    assert "考研方案B先准备材料" in text_of(result)
    assert any(value["id"] == assistant["id"] for value in result.alias_map.values())


def test_same_timestamp_earlier_run_is_rejected_after_a_new_user_source(memory: MemoryService) -> None:
    first = receive(memory, "较早问题", "first")
    receive(memory, "相同时刻后到的新问题", "second")
    with pytest.raises(ContextInputError) as error:
        build(memory, first)
    assert error.value.code == "context_current_not_latest"


def test_later_assistant_at_same_timestamp_is_not_injected(memory: MemoryService) -> None:
    current = receive(memory, "当前问题")
    memory.record_assistant_message("alice", "self", "life:self", "尚未消费的未来回答", run_id="future", channel="web")
    result = build(memory, current, query="未来回答")
    assert "尚未消费的未来回答" not in text_of(result)


def test_memory_validity_and_now_block_cannot_use_different_clocks(memory: MemoryService) -> None:
    source = receive(memory, "当前问题")
    other_clock = FrozenClock(datetime(2020, 1, 1, tzinfo=UTC))
    engine = ContextEngine(memory, "合成系统", clock=other_clock)
    with pytest.raises(ContextInputError) as error:
        engine.build("alice", source["id"])
    assert error.value.code == "context_clock_mismatch"


def test_same_transaction_and_message_timestamp_cannot_guess_consumption_order(memory: MemoryService) -> None:
    with memory.repo.transaction("alice"):
        first = receive(memory, "同一事务中的第一条", "one")
        second = receive(memory, "同一事务中的第二条", "two")
    current = max((first, second), key=lambda row: row["id"])
    with pytest.raises(ContextInputError) as error:
        build(memory, current)
    assert error.value.code == "context_source_order_ambiguous"

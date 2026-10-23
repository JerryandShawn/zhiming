"""Real PG L4 ranking preserves source versions, withdrawal and bounded fallback."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from typing import Any

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_types import BudgetPolicy
from mingjing_core.application.memory import MemoryService
from mingjing_core.timekit.clock import FrozenClock, set_clock
from tools.eval.targets.v4_target import V4Target

from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive


def l4(memory: MemoryService, source: dict[str, Any], limit: int = 10) -> tuple[Any, list[dict]]:
    context = ContextEngine(memory, "合成时间检索", policy=replace(BudgetPolicy(), search_limit=limit)).build(
        "alice", source["id"]
    )
    layer = next(layer for layer in context.budget.layers if layer.name == "L4")
    values = []
    for item in layer.items:
        if item.key != "time-filter":
            text = item.messages[0].content
            values.append(json.loads(text.splitlines()[1]))
    return context, values


def test_original_said_at_not_execution_or_creation_time_sets_the_month(memory: MemoryService) -> None:
    old = receive(memory, "想买一台微单相机", "camera", at="2026-09-14T10:00:00+08:00")
    receive(memory, "想换个降噪耳机", "headphones", at="2026-10-05T10:00:00+08:00")
    source = receive(memory, "上个月我说想买什么来着？", "month-query")
    set_clock(FrozenClock(datetime.fromisoformat("2026-11-17T10:30:00+08:00")))
    context, values = l4(memory, source)
    assert any('time_filter="2026-09-01..2026-09-30"' in message.content for message in context.messages)
    assert values[0]["text"] == old["content"] and values[0]["time_match"] is True
    assert context.injected_versions["message:" + old["id"]] == old["revision"]


def test_event_fact_uses_event_day_and_keeps_its_real_original_dependency(memory: MemoryService) -> None:
    original = receive(memory, "请记住我2026-10-21参加合成面试", "event-source", at="2026-09-14T10:00:00+08:00")
    fact = memory.save_fact("alice", "self", original["id"], original["content"], "background")
    fact = memory.repo.update(
        "alice",
        "fact",
        fact["id"],
        {"event_at": "2026-10-21", "requested_kind": "event"},
        expected_revision=fact["revision"],
    )
    source = receive(memory, "下周三的面试是什么安排？", "event-query")
    context, values = l4(memory, source, 1)
    assert len(values) == 1 and values[0]["kind"] == "fact" and values[0]["time_match"] is True
    assert context.injected_versions["fact:" + fact["id"]] == fact["revision"]
    assert context.injected_versions["message:" + original["id"]] == original["revision"]


def test_time_matches_first_then_unfiltered_fills_to_k_without_duplicate_ids(memory: MemoryService) -> None:
    matching = receive(memory, "相机安排在上个月", "matching", at="2026-09-14T10:00:00+08:00")
    receive(memory, "相机安排这周再看", "later-one", at="2026-10-15T10:00:00+08:00")
    receive(memory, "相机安排改为明天", "later-two", at="2026-10-16T10:00:00+08:00")
    source = receive(memory, "上个月相机的安排", "fallback-query")
    context, values = l4(memory, source, 3)
    assert len(values) == 3 and values[0]["text"] == matching["content"]
    assert [value["time_match"] for value in values] == [True, False, False]
    assert len({value["alias"] for value in values}) == 3
    assert context.read_counts["search_candidates"] <= 100


def test_holiday_window_is_current_year_published_arrangement(memory: MemoryService) -> None:
    original = receive(
        memory, "国庆回老家，和表哥因为合伙开店的事闹得不愉快", "holiday", at="2026-10-03T10:00:00+08:00"
    )
    receive(memory, "办的健身卡，健身房跑路了", "other-topic", at="2026-10-12T10:00:00+08:00")
    source = receive(memory, "国庆那几天我跟你说过什么烦心事？", "holiday-query")
    context, values = l4(memory, source)
    assert any('time_filter="2026-10-01..2026-10-07"' in message.content for message in context.messages)
    assert values and values[0]["text"] == original["content"] and values[0]["time_match"] is True


def test_foreign_owner_and_withdrawn_original_do_not_enter_time_results(memory: MemoryService) -> None:
    original = receive(memory, "相机是私人合成词", "withdrawn", at="2026-09-14T10:00:00+08:00")
    memory.receive("bob", content="相机来自另一个主人", source_id="foreign", at="2026-09-14T10:00:00+08:00")
    with memory.repo.transaction("alice") as connection:
        memory.repo.revoke(
            connection,
            "alice",
            "source_span",
            "withdrawn-camera",
            "stopped",
            {"message_id": original["id"], "start": 0, "end": len(original["content"])},
        )
    source = receive(memory, "上个月相机", "privacy-query")
    context, values = l4(memory, source)
    assert values == []
    assert all(
        original["content"] not in message.content and "另一个主人" not in message.content
        for message in context.messages
    )


def test_undefined_season_does_not_turn_into_a_full_year_filter(memory: MemoryService) -> None:
    source = receive(memory, "去年冬天我跟你说过想去哪旅游？", "season-query")
    context, values = l4(memory, source)
    assert values == [] and all('time_filter="2025' not in message.content for message in context.messages)


def test_v4_target_cannot_teach_the_parser_a_wrong_date_from_script_arguments(memory: MemoryService) -> None:
    text = "我下周三参加面试，请记住"
    target = V4Target(dsn=memory.repo.dsn)
    try:
        target.reset(
            {
                "synthetic": True,
                "_scenario_id": "date-parser-attack",
                "_scripted": [
                    {
                        "turn": 1,
                        "model": [
                            {
                                "tool_call": {
                                    "name": "memory_write",
                                    "arguments": {
                                        "message_id": "turn-1",
                                        "quote": text,
                                        "summary": "合成面试",
                                        "kind": "event",
                                        "event_at": "2026-10-28",
                                    },
                                }
                            },
                            {"text": "需要先核对日期。"},
                        ],
                    }
                ],
            }
        )
        result = target.send({"_index": 1, "user": text, "channel": "web"})
        assert result.error is None
        observed = target.inspect_db()
        assert observed["observed_tools"][0]["output"]["receipt"]["code"] == "date_conflict"
        assert not [row for row in observed["entities"] if row["kind"] == "fact"]
    finally:
        target.close()

"""Layer order, append-only windows and derived lineage use real PostgreSQL."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_types import ContextBuild, ContextInputError
from mingjing_core.application.memory import MemoryService
from mingjing_core.timekit.clock import get_clock

from .test_context_pg import build, receive
from .test_context_pg import context_memory_fixture as context_memory_fixture


def block(result: ContextBuild, name: str) -> list[str]:
    return [
        message.content
        for layer in result.budget.layers
        if layer.name == name
        for item in layer.items
        for message in item.messages
    ]


def derived(memory: MemoryService, kind: str, ident: str, source: dict[str, Any], **data: Any) -> dict[str, Any]:
    # Direct entity producer fixtures test the reader's hostile/stale input boundary.
    return memory.repo.put(
        "alice", kind, ident, dict(source_ids=[source["id"]], thread_id="life:self", **data), expected_revision=0
    )


def test_layer_order_and_stable_prefix_before_append_only_history(memory: MemoryService) -> None:
    source = receive(memory, "请记住，我不能上夜班", "constraint")
    memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    first = build(memory, receive(memory, "第一轮", "a"))
    second = build(memory, receive(memory, "第二轮", "b"))
    assert [layer.name for layer in second.budget.layers] == [
        "L0",
        "L2",
        "L3_STABLE",
        "L5",
        "L4",
        "L3_VOLATILE",
        "L1",
        "L6",
        "CYCLE",
    ]
    for name in ("L0", "L2", "L3_STABLE"):
        assert block(first, name) == block(second, name)
    assert block(second, "L5")[: len(block(first, "L5"))] == block(first, "L5")
    assert len(block(second, "L5")) == len(block(first, "L5")) + 1


def test_history_window_advances_in_ten_round_chunks_and_aliases_remain_stable(memory: MemoryService) -> None:
    snapshots = {}
    for index in range(1, 52):
        source = receive(memory, f"轮次内容{index:03d}", str(index))
        if index in {40, 41, 50, 51}:
            snapshots[index] = build(memory, source)
        get_clock().advance(timedelta(minutes=1))
    assert not any("线程窗口" in value for value in block(snapshots[40], "L5"))
    for index, start in ((41, 10), (50, 10), (51, 20)):
        values = block(snapshots[index], "L5")
        header = json.loads(values[0].splitlines()[1])
        assert header["window_start_round"] == start
        assert len(values) == index - start
        assert f"轮次内容{start + 1:03d}" in values[1]
        assert f"〔m{start + 1}〕" in values[1]
        assert f"轮次内容{index:03d}" not in "\n".join(values)
    assert block(snapshots[50], "L5")[: len(block(snapshots[41], "L5"))] == block(snapshots[41], "L5")


def test_only_selected_case_and_latest_three_valid_events_enter_stable_layer(memory: MemoryService) -> None:
    source = receive(memory, "准备考研", "goal")
    chosen = memory.create_case("alice", "self", "考研事项", goal=source["content"], message_id=source["id"])
    memory.create_case("alice", "self", "不可泄露事项")
    for index in range(5):
        memory.repo.put(
            "alice",
            "feedback",
            f"feedback-{index}",
            {
                "content": f"合成进展{index}",
                "source_ids": [source["id"]],
                "kind": "event",
                "thread_id": "life:self",
                "occurred_at": f"2026-10-{index + 1:02d}",
            },
            case_id=chosen["id"],
            expected_revision=0,
        )
    result = build(memory, receive(memory, "看看进展"), case_ids=(chosen["id"],))
    text = "\n".join(block(result, "L3_STABLE"))
    assert "不可泄露" not in text and "合成进展0" not in text and "合成进展1" not in text
    assert all(f"合成进展{index}" in text for index in (2, 3, 4))
    assert sum(value["kind"] == "feedback" for value in result.alias_map.values()) == 3


def test_derived_notes_are_relevant_labelled_and_disappear_after_source_withdrawal(memory: MemoryService) -> None:
    source = receive(memory, "考研安排", "origin")
    derived(memory, "note", "note-visible", source, content="考研时可以先整理计划")
    derived(memory, "note", "note-unrelated", source, content="火星卫星")
    current = receive(memory, "考研计划")
    result = build(memory, current)
    text = "\n".join(block(result, "L4"))
    assert "考研时可以先整理计划" in text and "明镜推测笔记" in text and "火星" not in text
    memory.repo.delete("alice", "message", source["id"], expected_revision=source["revision"])
    result = build(memory, current)
    assert "考研时可以先整理计划" not in "\n".join(block(result, "L4"))
    assert all(value["id"] != "note-visible" for value in result.alias_map.values())


@pytest.mark.parametrize(
    "changes", [{"source_ids": None}, {"source_refs": ["bad"]}, {"used_fact_ids": "bad"}, {"fact_ids": [True]}]
)
def test_malformed_derived_lineage_fails_closed(memory: MemoryService, changes: dict[str, Any]) -> None:
    source = receive(memory, "考研", "original")
    payload = dict(
        source_ids=[source["id"]],
        content="考研推测",
        **{key: value for key, value in changes.items() if key != "source_ids"},
    )
    if "source_ids" in changes:
        payload["source_ids"] = changes["source_ids"]
    memory.repo.put("alice", "note", "hostile-note", payload, expected_revision=0)
    with pytest.raises(ContextInputError):
        build(memory, receive(memory, "考研安排"))


def test_entity_catalog_overflow_is_explicit(memory: MemoryService) -> None:
    source = receive(memory, "考研", "original")
    derived(memory, "note", "note-1", source, content="考研甲")
    derived(memory, "note", "note-2", source, content="考研乙")
    from mingjing_core.agent.context_types import BudgetPolicy

    engine = ContextEngine(memory, "合成系统", policy=BudgetPolicy(extra_entity_limit=1))
    with pytest.raises(ContextInputError) as error:
        engine.build("alice", receive(memory, "考研安排")["id"])
    assert error.value.code == "context_entity_catalog_overflow"

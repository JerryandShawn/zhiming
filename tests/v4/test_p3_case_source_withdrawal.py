"""Partial case erasure keeps independent labels and never retains raw withdrawn quotes."""

from __future__ import annotations

import json

from mingjing_core.agent.context import ContextEngine
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository


def test_unrelated_goal_survives_but_its_broad_source_quote_is_removed(p2_repo: PostgresRepository) -> None:
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="请记住，我准备考研。家里养了一只猫", source_id="source")
    fact = memory.save_fact("alice", "self", source["id"], "我准备考研", "goal")
    case = memory.create_case("alice", "self", "独立标签", goal="家里养了一只猫", message_id=source["id"])
    old = p2_repo.update(
        "alice",
        "case",
        case["id"],
        {
            "source_refs": [
                {
                    "message_id": source["id"],
                    "version": source["revision"],
                    "start": 0,
                    "end": len(source["content"]),
                    "quote": source["content"],
                }
            ]
        },
        expected_revision=case["revision"],
    )
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    row = p2_repo.get("alice", "case", old["id"])
    assert row["state"]["goal"] == "家里养了一只猫" and row["title"] == "独立标签"
    assert "我准备考研" not in json.dumps(row, ensure_ascii=False)
    current = memory.receive("alice", content="看看猫的近况", source_id="current")
    context = ContextEngine(memory, "合成系统").build("alice", current["id"], case_ids=(row["id"],))
    text = "\n".join(
        message.content
        for layer in context.budget.layers
        if layer.name == "L3_STABLE"
        for item in layer.items
        for message in item.messages
    )
    assert "家里养了一只猫" in text and "我准备考研" not in text


def test_source_bound_title_and_goal_are_erased_without_deleting_case_id(p2_repo: PostgresRepository) -> None:
    memory = MemoryService(p2_repo)
    source = memory.receive("alice", content="请记住，我准备考研", source_id="source")
    fact = memory.save_fact("alice", "self", source["id"], "我准备考研", "goal")
    case = memory.create_case("alice", "self", "我准备考研", goal="我准备考研", message_id=source["id"])
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    row = p2_repo.get("alice", "case", case["id"])
    assert row["id"] == case["id"] and row["state"]["goal"] == "" and row["title"] == "已撤销的事项"
    assert "我准备考研" not in json.dumps(row, ensure_ascii=False)
    revision = row["revision"]
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    assert p2_repo.get("alice", "case", case["id"])["revision"] == revision


def test_new_independent_support_preserves_current_goal(p2_repo: PostgresRepository) -> None:
    memory = MemoryService(p2_repo)
    old = memory.receive("alice", content="请记住，我准备考研", source_id="old")
    fact = memory.save_fact("alice", "self", old["id"], "我准备考研", "goal")
    case = memory.create_case("alice", "self", "独立标签", goal="我准备考研", message_id=old["id"])
    new = memory.receive("alice", content="现在仍然是我准备考研", source_id="new")
    refs = [*case["source_refs"], {"message_id": new["id"], "version": new["revision"]}]
    p2_repo.update("alice", "case", case["id"], {"source_refs": refs}, expected_revision=case["revision"])
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"])
    row = p2_repo.get("alice", "case", case["id"])
    assert row["state"]["goal"] == "我准备考研"
    assert all(ref["message_id"] == new["id"] for ref in row["source_refs"])

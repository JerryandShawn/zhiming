"""R14 is driven by original words and real facts, never a model's change flag."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_explicit_changes import MemoryExplicitChangeService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.change_signals import explicit_replacement_slot

from .test_memory2_slots_pg import fact, slots_repo
from .test_memory2_slots_pg import undo as undo_slot


@pytest.fixture(name="tool_repo")
def explicit_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize(
    "before,after,slot",
    [
        ("我在杭州工作", "我搬到上海了", "residence_city"),
        ("我住在合成甲市", "我已经搬到合成乙市了", "residence_city"),
        ("我不吃辣", "最近开始能吃点辣了", "spice_preference"),
        ("我能吃辣", "我现在不吃辣了", "spice_preference"),
    ],
)
def test_explicit_changes_update_one_current_value_and_exact_undo(tool_repo: Any, before: str, after: str, slot: str):
    old = fact(tool_repo, before, "2026-10-03T10:30:00+08:00")
    new = fact(tool_repo, after, "2026-10-10T10:30:00+08:00")
    service = MemoryExplicitChangeService(V4FactMemory(tool_repo))
    args = dict(expected_old_revision=old["revision"], expected_new_revision=new["revision"], operation_id="r14")
    receipt = service.update("alice", "self", old["id"], new["id"], **args)
    assert receipt["write_status"] == "updated"
    assert service.memory.facts("alice")[0]["id"] == new["id"]
    current = tool_repo.get("alice", "fact", new["id"])
    previous = tool_repo.get("alice", "fact", old["id"])
    assert current["slot"] == slot and previous["valid_to"] == current["valid_from"]
    assert previous["status"] == "active" and previous["content"] == before
    revision = tool_repo.get_revision("alice")
    assert service.update("alice", "self", old["id"], new["id"], **args) == receipt
    assert tool_repo.get_revision("alice") == revision
    tool_repo.put("alice", "note", "r14-derived", {"fact_ids": [new["id"]]}, expected_revision=0)
    undo_slot(tool_repo, receipt)
    restored = tool_repo.get("alice", "fact", old["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in restored.items() if k not in reserved} == {
        k: v for k, v in old.items() if k not in reserved
    }
    assert tool_repo.get("alice", "note", "r14-derived", include_deleted=True)["status"] == "deleted"


@pytest.mark.parametrize(
    "after",
    ["我在上海上班", "如果我搬到上海了？", "我朋友搬到上海了", "我临时搬到上海了", "我没有搬到上海了"],
)
def test_uncertain_or_unchanged_statements_cannot_trigger_direct_replacement(tool_repo: Any, after: str):
    assert explicit_replacement_slot("我在杭州工作", after) is None
    old = fact(tool_repo, "我在杭州工作", "2026-10-03T10:30:00+08:00")
    if "如果" in after:
        return
    new = fact(tool_repo, after, "2026-10-10T10:30:00+08:00")
    with pytest.raises(EvidenceError):
        MemoryExplicitChangeService(V4FactMemory(tool_repo)).update(
            "alice",
            "self",
            old["id"],
            new["id"],
            expected_old_revision=old["revision"],
            expected_new_revision=new["revision"],
            operation_id="uncertain-r14",
        )
    assert tool_repo.get("alice", "fact", old["id"]) == old


def test_multiple_old_cities_need_confirmation_and_wrong_owner_cannot_update(tool_repo: Any):
    old = fact(tool_repo, "我在杭州工作", "2026-10-03T10:30:00+08:00")
    fact(tool_repo, "我住在合成甲市", "2026-10-04T10:30:00+08:00")
    new = fact(tool_repo, "我搬到上海了", "2026-10-10T10:30:00+08:00")
    service = MemoryExplicitChangeService(V4FactMemory(tool_repo))
    args = dict(expected_old_revision=old["revision"], expected_new_revision=new["revision"], operation_id="ambiguous")
    with pytest.raises(EvidenceError):
        service.update("alice", "self", old["id"], new["id"], **args)
    with pytest.raises(ScopeError):
        service.update("bob", "self", old["id"], new["id"], **args)
    assert tool_repo.get("alice", "fact", old["id"]) == old

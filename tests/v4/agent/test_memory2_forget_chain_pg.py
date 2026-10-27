"""Privacy withdrawal repairs both ends through the real fact service and PG."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.domain.contracts import EvidenceError

from .test_memory2_conflict_resolution_pg import choose
from .test_memory2_conflicts_pg import conflict
from .test_memory2_slots_pg import fact, pair, undo, update
from .test_memory2_slots_pg import slots_repo as base_slots_repo
from .test_toolkit_pg import setup


@pytest.fixture(name="tool_repo")
def chain_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_slots_repo.__wrapped__(p2_repo, monkeypatch)


def forget(repo: Any, row: dict, **changes: Any) -> dict:
    current = repo.get("alice", "fact", row["id"])
    return V4FactMemory(repo).retire_fact("alice", row["id"], expected_revision=current["revision"], **changes)


@pytest.mark.parametrize("operation", ["delete", "stop"])
def test_forgetting_new_value_restores_only_the_authorized_old_endpoint(tool_repo: Any, operation: str) -> None:
    old, new = pair(tool_repo)
    receipt = update(tool_repo, old, new)
    tool_repo.put(
        "alice",
        "note",
        "synthetic-new-note",
        {"fact_ids": [new["id"]]},
        expected_revision=0,
    )
    result = forget(tool_repo, new, operation=operation)
    restored = tool_repo.get("alice", "fact", old["id"])
    assert restored.get("valid_to") is None and restored.get("superseded_by") is None
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [old["id"]]
    assert result["affected_fact_ids"] == [new["id"]]
    assert tool_repo.get("alice", "note", "synthetic-new-note", include_deleted=True)["status"] == "deleted"
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt)


def test_forgetting_old_value_detaches_new_value_without_rewriting_its_source(
    tool_repo: Any,
) -> None:
    old, new = pair(tool_repo)
    receipt = update(tool_repo, old, new)
    before = tool_repo.get("alice", "fact", new["id"])
    forget(tool_repo, old)
    after = tool_repo.get("alice", "fact", new["id"])
    assert after["supersedes"] is None and after["content"] == before["content"]
    assert after["source_refs"] == before["source_refs"] and after["valid_from"] == before["valid_from"]
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [new["id"]]
    assert tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)["status"] == "deleted"


def test_real_memory_forget_tool_restores_prior_current_value_and_replay_is_stable(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    update(tool_repo, old, new)
    h = setup(tool_repo, "请忘记这条记忆：" + new["content"])
    args = {"fact_id": new["id"], "message_id": h.source["id"]}
    result, ctx = h.call("memory_forget", args)
    assert result.ok and result.receipt["write_status"] == "deleted"
    assert [row["id"] for row in h.service.memory.facts("alice")] == [old["id"]]
    revision = tool_repo.get_revision("alice")
    assert h.registry.execute("memory_forget", args, ctx) == result
    assert tool_repo.get_revision("alice") == revision


def test_middle_withdrawal_splices_neighbors_without_two_current_values(
    tool_repo: Any,
) -> None:
    first, middle = pair(tool_repo)
    update(tool_repo, first, middle)
    middle = tool_repo.get("alice", "fact", middle["id"])
    last = fact(tool_repo, "我搬到合成第三城了", "2026-10-19T10:00:00+08:00")
    update(tool_repo, middle, last, operation_id="synthetic-chain-third")
    forget(tool_repo, middle)
    before, after = (
        tool_repo.get("alice", "fact", first["id"]),
        tool_repo.get("alice", "fact", last["id"]),
    )
    assert before["superseded_by"] == last["id"] and after["supersedes"] == first["id"]
    assert before["valid_to"] == after["valid_from"]
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [last["id"]]
    forget(tool_repo, last)
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [first["id"]]
    restored = tool_repo.get("alice", "fact", first["id"])
    assert restored.get("valid_to") is None and restored.get("superseded_by") is None


def test_source_scope_withdrawal_cannot_restore_another_fact_in_the_same_batch(
    tool_repo: Any,
) -> None:
    old, new = pair(tool_repo)
    new = tool_repo.update(
        "alice",
        "fact",
        new["id"],
        {"source_refs": [*new["source_refs"], *old["source_refs"]]},
        expected_revision=new["revision"],
    )
    update(tool_repo, old, new)
    result = forget(tool_repo, new, scope="source")
    assert set(result["affected_fact_ids"]) == {old["id"], new["id"]}
    assert V4FactMemory(tool_repo).facts("alice") == []
    assert all(row["status"] == "deleted" for row in tool_repo.list("alice", "fact", include_deleted=True))


def test_later_edit_does_not_restore_a_historical_value_without_current_snapshot(
    tool_repo: Any,
) -> None:
    old, new = pair(tool_repo)
    update(tool_repo, old, new)
    current = tool_repo.get("alice", "fact", old["id"])
    tool_repo.update(
        "alice",
        "fact",
        old["id"],
        {"summary": "合成用户编辑"},
        expected_revision=current["revision"],
    )
    forget(tool_repo, new)
    previous = tool_repo.get("alice", "fact", old["id"])
    assert previous["summary"] == "合成用户编辑" and previous["valid_to"] is not None
    assert previous["superseded_by"] is None and V4FactMemory(tool_repo).facts("alice") == []


def test_invalid_old_source_is_never_restored_by_forgetting_new_value(
    tool_repo: Any,
) -> None:
    old, new = pair(tool_repo)
    update(tool_repo, old, new)
    source = tool_repo.get("alice", "message", old["source_refs"][0]["message_id"])
    tool_repo.update(
        "alice",
        "message",
        source["id"],
        {"synthetic_edit": True},
        expected_revision=source["revision"],
    )
    forget(tool_repo, new)
    assert tool_repo.get("alice", "fact", old["id"])["valid_to"] is not None
    assert V4FactMemory(tool_repo).facts("alice") == []


def test_conflict_selected_new_value_uses_the_same_chain_forgetting_path(
    tool_repo: Any,
) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    selected = choose(h, pending)
    forget(tool_repo, {"id": selected["fact_id"]})
    previous = tool_repo.get("alice", "fact", old["id"])
    assert previous.get("valid_to") is None and previous.get("superseded_by") is None
    assert [row["id"] for row in h.service.memory.facts("alice")] == [old["id"]]
    proposal = tool_repo.get("alice", "proposal", pending.receipt["id"], include_deleted=True)
    assert proposal["status"] == "deleted" and "old_before" not in proposal


def test_corrupt_two_node_cycle_cannot_block_privacy_deletion(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    boundary = "2026-10-18T10:00:00+08:00"
    for row, other in ((old, new), (new, old)):
        tool_repo.update(
            "alice",
            "fact",
            row["id"],
            {"supersedes": other["id"], "superseded_by": other["id"], "valid_from": boundary, "valid_to": boundary},
            expected_revision=row["revision"],
        )
    forget(tool_repo, new)
    assert tool_repo.get("alice", "fact", new["id"], include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "fact", old["id"])["valid_to"] == boundary

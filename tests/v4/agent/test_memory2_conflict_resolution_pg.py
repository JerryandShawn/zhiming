"""Explicit new/old choices and undo use real P3 proposals and isolated PostgreSQL."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from mingjing_core.application.memory2_conflict_resolution import (
    REMEMBER,
    USE_NEW,
    USE_OLD,
)
from mingjing_core.application.memory2_conflict_resolution_undo import UNDO_CONFLICT
from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_conflicts_pg import conflict
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as base_tool_repo

NOW = datetime.fromisoformat("2026-10-24T00:00:00+08:00")


@pytest.fixture(name="tool_repo")
def resolution_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(NOW))
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def choose(h: Any, pending: Any, choice: str = "new", *, key: str = "synthetic-choice", remember: bool = False) -> dict:
    text = USE_OLD if choice == "old" else USE_NEW + (REMEMBER if remember else "")
    action = h.service.memory.receive("alice", content=text, source_id=key, channel="synthetic")
    return MemoryProposalService(h.service.memory).resolve_conflict(
        "alice",
        "self",
        pending.receipt["id"],
        expected_revision=pending.receipt["revision"],
        message_id=action["id"],
        choice=choice,
        remember_category=remember,
        operation_id=key,
    )


def undo(h: Any, pending: Any, *, key: str = "synthetic-undo-choice") -> dict:
    action = h.service.memory.receive("alice", content=UNDO_CONFLICT, source_id=key, channel="synthetic")
    return MemoryProposalService(h.service.memory).undo_conflict(
        "alice",
        "self",
        pending.receipt["id"],
        expected_revision=2,
        message_id=action["id"],
        operation_id=key,
    )


def test_new_choice_changes_only_current_truth_and_undo_restores_exact_old_payload(tool_repo: Any) -> None:
    h, old, pending, ctx, args = conflict(tool_repo)
    selected = choose(h, pending)
    new = tool_repo.get("alice", "fact", selected["fact_id"])
    previous = tool_repo.get("alice", "fact", old["id"])
    assert selected["write_status"] == "updated" and new["content"] == "我不喜欢合成徒步"
    assert previous["status"] == "active" and previous["superseded_by"] == new["id"]
    assert new["supersedes"] == old["id"] and previous["valid_to"] == new["valid_from"]
    assert [row["id"] for row in h.service.memory.facts("alice")] == [new["id"]]
    revision = tool_repo.get_revision("alice")
    assert choose(h, pending) == selected and tool_repo.get_revision("alice") == revision
    assert not h.registry.execute("memory_write", args, ctx).ok
    tool_repo.put("alice", "note", "synthetic-new-value", {"fact_ids": [new["id"]]}, expected_revision=0)
    restored = undo(h, pending)
    reserved = {"revision", "created_at", "updated_at"}
    current = tool_repo.get("alice", "fact", old["id"])
    assert {k: v for k, v in current.items() if k not in reserved} == {
        k: v for k, v in old.items() if k not in reserved
    }
    assert tool_repo.get("alice", "fact", new["id"])["status"] == "retired"
    assert tool_repo.get("alice", "consent", new["approval_consent_id"], include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "note", "synthetic-new-value", include_deleted=True)["status"] == "deleted"
    proposal = tool_repo.get("alice", "proposal", pending.receipt["id"])
    assert proposal["status"] == "pending" and proposal["target_revision"] == restored["revision"]
    revision = tool_repo.get_revision("alice")
    assert undo(h, pending) == restored and tool_repo.get_revision("alice") == revision
    with pytest.raises(EvidenceError):
        choose(h, pending)


def test_old_choice_has_no_new_fact_or_consent_and_can_be_undone(tool_repo: Any) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    selected = choose(h, pending, "old")
    assert selected["write_status"] == "stopped" and tool_repo.list("alice", "consent") == []
    assert tool_repo.get("alice", "fact", old["id"])["revision"] == old["revision"]
    tool_repo.put(
        "alice", "note", "synthetic-selection-note", {"source_ids": [pending.receipt["id"]]}, expected_revision=0
    )
    restored = undo(h, pending)
    assert restored["affected_ids"] == []
    assert tool_repo.get("alice", "proposal", pending.receipt["id"])["status"] == "pending"
    assert tool_repo.get("alice", "note", "synthetic-selection-note", include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "fact", old["id"])["revision"] == old["revision"]


def test_reconfirmation_uses_new_fact_identity_and_does_not_revive_retired_result(tool_repo: Any) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    selected = choose(h, pending)
    undo(h, pending)
    proposal = tool_repo.get("alice", "proposal", pending.receipt["id"])
    action = h.service.memory.receive(
        "alice", content=USE_NEW, source_id="synthetic-fresh-rechoice", channel="synthetic"
    )
    fresh = MemoryProposalService(h.service.memory).resolve_conflict(
        "alice",
        "self",
        proposal["id"],
        expected_revision=proposal["revision"],
        message_id=action["id"],
        choice="new",
        operation_id="synthetic-fresh-rechoice",
    )
    assert fresh["fact_id"] != selected["fact_id"]
    assert tool_repo.get("alice", "fact", selected["fact_id"])["status"] == "retired"
    assert [row["id"] for row in h.service.memory.facts("alice")] == [fresh["fact_id"]]


def test_one_user_action_cannot_select_two_proposals(tool_repo: Any) -> None:
    h, _, pending, _, _ = conflict(tool_repo)
    choose(h, pending, "old")
    h.finish()
    second = setup(tool_repo, "我不喜欢合成徒步")
    another, _, _ = second.write("preference")
    first_action = h.service.memory.receive("alice", content=USE_OLD, source_id="synthetic-choice", channel="synthetic")
    with pytest.raises(EvidenceError):
        MemoryProposalService(h.service.memory).resolve_conflict(
            "alice",
            "self",
            another.receipt["id"],
            expected_revision=another.receipt["revision"],
            message_id=first_action["id"],
            choice="old",
            operation_id="synthetic-second-choice",
        )
    assert tool_repo.get("alice", "proposal", another.receipt["id"])["status"] == "pending"


@pytest.mark.parametrize(
    "text,role,private", [("请保存这条记忆", "user", False), (USE_NEW, "assistant", False), (USE_NEW, "user", True)]
)
def test_new_truth_requires_explicit_current_nonprivate_user_choice(
    tool_repo: Any, text: str, role: str, private: bool
) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    action = h.service.memory.receive(
        "alice", content=text, role=role, source_id="synthetic-invalid-choice", channel="synthetic"
    )
    if private:
        action = tool_repo.update(
            "alice", "message", action["id"], {"incognito": True}, expected_revision=action["revision"]
        )
    with pytest.raises(EvidenceError):
        MemoryProposalService(h.service.memory).resolve_conflict(
            "alice",
            "self",
            pending.receipt["id"],
            expected_revision=1,
            message_id=action["id"],
            choice="new",
            operation_id="synthetic-invalid-choice",
        )
    assert [row["id"] for row in tool_repo.list("alice", "fact")] == [old["id"]]


def test_stale_revision_and_owner_cannot_select_a_conflict(tool_repo: Any) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    tool_repo.update("alice", "fact", old["id"], {"synthetic_edit": True}, expected_revision=old["revision"])
    with pytest.raises(RevisionConflict):
        choose(h, pending)
    with pytest.raises(ScopeError):
        MemoryProposalService(h.service.memory).resolve_conflict(
            "bob",
            "self",
            pending.receipt["id"],
            expected_revision=1,
            message_id=h.source["id"],
            choice="new",
            operation_id="synthetic-cross-owner-choice",
        )
    assert tool_repo.list("alice", "consent") == []


def test_later_user_edits_block_undo_without_overwriting_them(tool_repo: Any) -> None:
    h, _, pending, _, _ = conflict(tool_repo)
    selected = choose(h, pending)
    tool_repo.update(
        "alice", "fact", selected["fact_id"], {"summary": "合成用户修改"}, expected_revision=selected["revision"]
    )
    with pytest.raises(RevisionConflict):
        undo(h, pending)
    assert tool_repo.get("alice", "fact", selected["fact_id"])["summary"] == "合成用户修改"


def test_old_command_cannot_be_reused_for_a_later_conflict(tool_repo: Any) -> None:
    from mingjing_core.application.memory import MemoryService

    action = MemoryService(tool_repo).receive(
        "alice", content=USE_OLD, source_id="synthetic-earlier-choice", channel="synthetic"
    )
    h, old, pending, _, _ = conflict(tool_repo)
    with pytest.raises(EvidenceError, match="早于"):
        MemoryProposalService(h.service.memory).resolve_conflict(
            "alice", "self", pending.receipt["id"], expected_revision=1,
            message_id=action["id"], choice="old", operation_id="synthetic-replayed-old-command",
        )
    assert tool_repo.get("alice", "fact", old["id"])["revision"] == old["revision"]
    assert tool_repo.get("alice", "proposal", pending.receipt["id"])["status"] == "pending"


def test_undo_command_must_follow_the_choice_it_revokes(tool_repo: Any) -> None:
    h, _, pending, _, _ = conflict(tool_repo)
    action = h.service.memory.receive(
        "alice", content=UNDO_CONFLICT, source_id="synthetic-premature-undo", channel="synthetic"
    )
    selected = choose(h, pending)
    with pytest.raises(EvidenceError, match="早于"):
        MemoryProposalService(h.service.memory).undo_conflict(
            "alice", "self", pending.receipt["id"], expected_revision=2,
            message_id=action["id"], operation_id="synthetic-premature-undo",
        )
    assert tool_repo.get("alice", "fact", selected["fact_id"])["status"] == "active"


@pytest.mark.parametrize("target", ["old", "new"])
def test_forgotten_facts_purge_resolution_snapshot_and_never_revive(tool_repo: Any, target: str) -> None:
    h, old, pending, _, _ = conflict(tool_repo)
    selected = choose(h, pending)
    current = tool_repo.get("alice", "fact", old["id"] if target == "old" else selected["fact_id"])
    h.service.memory.retire_fact("alice", current["id"], expected_revision=current["revision"])
    proposal = tool_repo.get("alice", "proposal", pending.receipt["id"], include_deleted=True)
    assert proposal["status"] == "deleted" and "old_before" not in proposal
    with pytest.raises(EvidenceError):
        undo(h, pending)

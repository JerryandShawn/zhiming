"""Scripted reflection proposals require actual user confirmation and stay derived."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_profile_proposals import (
    ACCEPT_PROFILE,
    DISMISS_PROFILE,
    UNDO_PROFILE,
    ProfileProposalService,
)
from mingjing_core.application.memory2_profile_reflection import ProfileReflectionService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.profile_doc import SECTION_TITLES
from mingjing_core.models.port import ChatMessage, ToolSpec
from tools.eval.targets.v4_scripted import ScriptedModelPort

from .test_memory2_slots_pg import fact
from .test_memory2_slots_pg import slots_repo as base_slots_repo


@pytest.fixture(name="tool_repo")
def profile_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_slots_repo.__wrapped__(p2_repo, monkeypatch)


def candidate(repo: Any, *, item_id: str | None = None, text: str = "偏好合成徒步") -> tuple[dict, dict]:
    row = fact(repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    service = ProfileReflectionService(V4FactMemory(repo))
    snapshot = service.prepare("alice", "self", [row["id"]])
    receipt = service.propose(
        "alice",
        "self",
        [{"section": 5, "text": text, "fact_ids": [row["id"]], "item_id": item_id}],
        fact_versions=snapshot["fact_versions"],
        operation_id="synthetic-profile-propose:" + text,
    )
    return repo.get("alice", "proposal", receipt["ids"][0]), row


def act(
    repo: Any, proposal: dict, action: str = "accept", *, key: str = "synthetic-profile-accept", role: str = "user"
) -> dict:
    memory = V4FactMemory(repo)
    command = {"accept": ACCEPT_PROFILE, "dismiss": DISMISS_PROFILE, "undo": UNDO_PROFILE}[action]
    original = memory.receive("alice", content=command, role=role, source_id=key, channel="synthetic")
    return ProfileProposalService(memory).act(
        "alice",
        "self",
        proposal["id"],
        expected_revision=proposal["revision"],
        message_id=original["id"],
        action=action,
        operation_id=key,
    )


def test_scripted_background_output_creates_pending_sections_without_user_facts(tool_repo: Any) -> None:
    row = fact(tool_repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    service = ProfileReflectionService(V4FactMemory(tool_repo))
    snapshot = service.prepare("alice", "self", [row["id"]])
    model = ScriptedModelPort()
    suggestions = [
        {"section": section, "text": "合成待确认画像", "fact_ids": [row["id"]]}
        for section in SECTION_TITLES
        if section != 7
    ]
    ops = [
        {
            "op": "add",
            "section": value["section"],
            "text": value["text"],
            "source_ids": snapshot["facts"][0]["source_ids"],
        }
        for value in suggestions
    ]
    model.actions = [{"tool_call": {"name": "profile_doc_patch", "arguments": {"ops": ops}}}]
    result = model.complete(
        [ChatMessage("user", json.dumps(snapshot, ensure_ascii=False))],
        tools=[ToolSpec("profile_doc_patch", "合成反思建议", {})],
    )
    receipt = service.consume_patch(
        "alice",
        "self",
        result.tool_calls[0].arguments["ops"],
        fact_versions=snapshot["fact_versions"],
        operation_id="synthetic-scripted-profile",
    )
    assert len(snapshot["sections"]) == 8 and snapshot["unavailable_sections"].keys() == {7}
    assert len(receipt["ids"]) == 7 and model.calls == 1
    assert tool_repo.list("alice", "profile_doc") == []
    assert [item["id"] for item in tool_repo.list("alice", "fact")] == [row["id"]]
    revision = tool_repo.get_revision("alice")
    assert (
        service.propose(
            "alice",
            "self",
            suggestions,
            fact_versions=snapshot["fact_versions"],
            operation_id="synthetic-scripted-profile",
        )
        == receipt
    )
    assert tool_repo.get_revision("alice") == revision


def test_acceptance_and_undo_are_idempotent_and_do_not_turn_inference_into_fact(tool_repo: Any) -> None:
    proposal, fact_row = candidate(tool_repo)
    receipt = act(tool_repo, proposal)
    item = tool_repo.get("alice", "profile_doc", receipt["id"])
    assert item["inferred"] and item["confirmed_by_user"] and item["assertion_status"] == "derived"
    assert item["fact_ids"] == [fact_row["id"]]
    revision = tool_repo.get_revision("alice")
    assert act(tool_repo, proposal) == receipt and tool_repo.get_revision("alice") == revision
    resolved = tool_repo.get("alice", "proposal", proposal["id"])
    tool_repo.put("alice", "note", "synthetic-profile-use", {"source_ids": [item["id"]]}, expected_revision=0)
    undone = act(tool_repo, resolved, "undo", key="synthetic-profile-undo")
    assert tool_repo.get("alice", "profile_doc", item["id"], include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "note", "synthetic-profile-use", include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "proposal", proposal["id"])["status"] == "pending"
    revision = tool_repo.get_revision("alice")
    assert act(tool_repo, resolved, "undo", key="synthetic-profile-undo") == undone
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", fact_row["id"])["revision"] == fact_row["revision"]


def test_user_edited_pinned_item_is_only_proposed_and_exactly_restored_on_undo(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    receipt = act(tool_repo, proposal)
    item = tool_repo.update(
        "alice",
        "profile_doc",
        receipt["id"],
        {"edited_by_user": True, "pinned": True, "custom": "合成保留字段"},
        expected_revision=receipt["revision"],
    )
    next_proposal, _ = candidate(tool_repo, item_id=item["id"], text="新的合成画像建议")
    assert tool_repo.get("alice", "profile_doc", item["id"]) == item
    accepted = act(tool_repo, next_proposal, key="synthetic-profile-replace")
    after = tool_repo.get("alice", "profile_doc", accepted["id"])
    assert after["pinned"] and after["edited_by_user"] and after["custom"] == item["custom"]
    resolved = tool_repo.get("alice", "proposal", next_proposal["id"])
    act(tool_repo, resolved, "undo", key="synthetic-profile-replace-undo")
    restored = tool_repo.get("alice", "profile_doc", item["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in item.items() if k not in reserved} == {
        k: v for k, v in restored.items() if k not in reserved
    }


@pytest.mark.parametrize("mode", ["accept", "pending"])
def test_forgetting_a_fact_purges_profile_and_undo_snapshot(tool_repo: Any, mode: str) -> None:
    proposal, source_fact = candidate(tool_repo)
    accepted = act(tool_repo, proposal) if mode == "accept" else None
    V4FactMemory(tool_repo).retire_fact("alice", source_fact["id"], expected_revision=source_fact["revision"])
    deleted = tool_repo.get("alice", "proposal", proposal["id"], include_deleted=True)
    assert deleted["status"] == "deleted" and "profile_before" not in deleted
    if accepted:
        assert tool_repo.get("alice", "profile_doc", accepted["id"], include_deleted=True)["status"] == "deleted"


def test_later_edit_blocks_undo_without_losing_user_text(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    receipt = act(tool_repo, proposal)
    resolved = tool_repo.get("alice", "proposal", proposal["id"])
    tool_repo.update(
        "alice", "profile_doc", receipt["id"], {"text": "合成用户手改"}, expected_revision=receipt["revision"]
    )
    with pytest.raises(RevisionConflict):
        act(tool_repo, resolved, "undo", key="synthetic-profile-edit-undo")
    assert tool_repo.get("alice", "profile_doc", receipt["id"])["text"] == "合成用户手改"


def test_dismiss_is_body_free_replayable_and_requires_real_user_action(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    with pytest.raises(EvidenceError):
        act(tool_repo, proposal, "dismiss", key="synthetic-profile-assistant", role="assistant")
    receipt = act(tool_repo, proposal, "dismiss", key="synthetic-profile-dismiss")
    assert receipt["write_status"] == "stopped" and "text" not in receipt
    assert act(tool_repo, proposal, "dismiss", key="synthetic-profile-dismiss") == receipt


@pytest.mark.parametrize("bad", [7, 0, True, "5"])
def test_unknown_or_unattested_chart_sections_never_write(tool_repo: Any, bad: Any) -> None:
    source_fact = fact(tool_repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    service = ProfileReflectionService(V4FactMemory(tool_repo))
    with pytest.raises(EvidenceError):
        service.propose(
            "alice",
            "self",
            [{"section": bad, "text": "合成", "fact_ids": [source_fact["id"]]}],
            fact_versions={source_fact["id"]: source_fact["revision"]},
            operation_id="synthetic-invalid-section",
        )
    assert tool_repo.list("alice", "proposal") == []


def test_scope_staleness_and_private_input_are_checked_before_proposals(tool_repo: Any) -> None:
    proposal, source_fact = candidate(tool_repo)
    service = ProfileReflectionService(V4FactMemory(tool_repo))
    with pytest.raises(EvidenceError):
        service.prepare("alice", "self", [source_fact["id"]], incognito=True)
    with pytest.raises(ScopeError):
        service.prepare("bob", "self", [source_fact["id"]])
    tool_repo.update(
        "alice", "fact", source_fact["id"], {"summary": "合成变化"}, expected_revision=source_fact["revision"]
    )
    with pytest.raises(RevisionConflict):
        act(tool_repo, proposal)
    assert tool_repo.list("alice", "profile_doc") == []


def test_snapshot_cannot_commit_model_output_after_fact_changed(tool_repo: Any) -> None:
    row = fact(tool_repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    service = ProfileReflectionService(V4FactMemory(tool_repo))
    snapshot = service.prepare("alice", "self", [row["id"]])
    tool_repo.update("alice", "fact", row["id"], {"summary": "合成新版本"}, expected_revision=row["revision"])
    with pytest.raises(RevisionConflict):
        service.propose(
            "alice",
            "self",
            [{"section": 5, "text": "合成建议", "fact_ids": [row["id"]]}],
            fact_versions=snapshot["fact_versions"],
            operation_id="synthetic-profile-race",
        )
    assert tool_repo.list("alice", "proposal") == []


def test_profile_proposal_rejects_a_generated_credential_without_persisting_it(tool_repo: Any) -> None:
    row = fact(tool_repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    with pytest.raises(EvidenceError):
        ProfileReflectionService(V4FactMemory(tool_repo)).propose(
            "alice",
            "self",
            [{"section": 5, "text": "sk-" + "SyntheticOnly" * 3, "fact_ids": [row["id"]]}],
            fact_versions={row["id"]: row["revision"]},
            operation_id="synthetic-profile-secret",
        )
    assert tool_repo.list("alice", "proposal") == []


@pytest.mark.parametrize("sources", [[], ["unoffered-source"], [123]])
def test_patch_requires_actual_offered_sources(tool_repo: Any, sources: list) -> None:
    row = fact(tool_repo, "我喜欢合成徒步", "2026-10-17T10:00:00+08:00")
    with pytest.raises(EvidenceError):
        ProfileReflectionService(V4FactMemory(tool_repo)).consume_patch(
            "alice",
            "self",
            [{"op": "add", "section": 5, "text": "合成建议", "source_ids": sources}],
            fact_versions={row["id"]: row["revision"]},
            operation_id="synthetic-profile-bad-sources",
        )
    assert tool_repo.list("alice", "proposal") == []


def test_expired_event_is_not_current_profile_even_before_archival_task(tool_repo: Any) -> None:
    row = fact(
        tool_repo, "我准备参加合成活动", "2026-10-17T10:00:00+08:00", requested_kind="event", event_at="2026-10-17"
    )
    with pytest.raises(EvidenceError, match="过期"):
        ProfileReflectionService(V4FactMemory(tool_repo)).prepare("alice", "self", [row["id"]])

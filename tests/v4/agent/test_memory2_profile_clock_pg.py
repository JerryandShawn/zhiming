"""Profile actions cannot use an older statement clock to authorize a later suggestion."""

from __future__ import annotations

from datetime import datetime, timedelta
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
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock

from .test_memory2_profile_proposals_pg import candidate
from .test_memory2_slots_pg import slots_repo as base_slots_repo

NOW = datetime.fromisoformat("2026-10-24T06:00:00+08:00")


@pytest.fixture(name="tool_repo")
def profile_clock_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    repo = base_slots_repo.__wrapped__(p2_repo, monkeypatch)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(NOW))
    return repo


def action(repo: Any, proposal: dict, command: str, at: datetime, key: str, verb: str = "accept") -> dict:
    memory = V4FactMemory(repo)
    source = memory.receive("alice", content=command, source_id=key, channel="synthetic", at=at)
    return ProfileProposalService(memory).act(
        "alice",
        "self",
        proposal["id"],
        expected_revision=proposal["revision"],
        message_id=source["id"],
        action=verb,
        operation_id=key,
    )


@pytest.mark.parametrize("verb,command", [("accept", ACCEPT_PROFILE), ("dismiss", DISMISS_PROFILE)])
def test_backdated_action_before_new_proposal_is_rejected(tool_repo: Any, verb: str, command: str) -> None:
    proposal, _ = candidate(tool_repo)
    with pytest.raises(EvidenceError):
        action(tool_repo, proposal, command, NOW - timedelta(hours=1), "backdated-profile", verb)
    assert tool_repo.get("alice", "proposal", proposal["id"]) == proposal
    assert tool_repo.list("alice", "profile_doc") == []


def test_reopened_proposal_needs_an_action_after_undo(tool_repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    proposal, _ = candidate(tool_repo)
    action(tool_repo, proposal, ACCEPT_PROFILE, NOW, "initial-profile")
    accepted = tool_repo.get("alice", "proposal", proposal["id"])
    later = NOW + timedelta(hours=2)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(later))
    action(tool_repo, accepted, UNDO_PROFILE, later, "undo-profile", "undo")
    reopened = tool_repo.get("alice", "proposal", proposal["id"])
    with pytest.raises(EvidenceError):
        action(tool_repo, reopened, ACCEPT_PROFILE, NOW + timedelta(hours=1), "old-time-reaccept")
    assert tool_repo.get("alice", "proposal", proposal["id"]) == reopened
    assert tool_repo.list("alice", "profile_doc") == []


def test_fresh_actions_replay_without_rewriting_preparation_time(
    tool_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, _ = candidate(tool_repo)
    prepared = proposal["prepared_at"]
    receipt = action(tool_repo, proposal, ACCEPT_PROFILE, NOW, "fresh-profile")
    later = NOW + timedelta(hours=2)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(later))
    revision = tool_repo.get_revision("alice")
    assert action(tool_repo, proposal, ACCEPT_PROFILE, NOW, "fresh-profile") == receipt
    assert tool_repo.get_revision("alice") == revision
    accepted = tool_repo.get("alice", "proposal", proposal["id"])
    assert accepted["prepared_at"] == prepared
    undone = action(tool_repo, accepted, UNDO_PROFILE, later, "fresh-undo", "undo")
    revision = tool_repo.get_revision("alice")
    assert action(tool_repo, accepted, UNDO_PROFILE, later, "fresh-undo", "undo") == undone
    assert tool_repo.get_revision("alice") == revision
    reopened = tool_repo.get("alice", "proposal", proposal["id"])
    assert datetime.fromisoformat(reopened["prepared_at"]) == later
    again = action(tool_repo, reopened, ACCEPT_PROFILE, later, "fresh-reaccept")
    assert tool_repo.get("alice", "profile_doc", again["id"])["confirmed_by_user"] is True


def test_same_suggestion_in_another_operation_keeps_original_preparation(
    tool_repo: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal, row = candidate(tool_repo)
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", FrozenClock(NOW + timedelta(hours=1)))
    revision = tool_repo.get_revision("alice")
    receipt = ProfileReflectionService(V4FactMemory(tool_repo)).propose(
        "alice",
        "self",
        [{"section": 5, "text": proposal["text"], "fact_ids": [row["id"]], "item_id": None}],
        fact_versions=proposal["input_fact_versions"],
        operation_id="repeat-profile-proposal",
    )
    assert receipt["ids"] == [proposal["id"]]
    assert tool_repo.get("alice", "proposal", proposal["id"]) == proposal
    assert tool_repo.get_revision("alice") == revision


def test_dismissed_suggestion_is_not_recreated_by_another_operation(tool_repo: Any) -> None:
    proposal, row = candidate(tool_repo)
    action(tool_repo, proposal, DISMISS_PROFILE, NOW, "dismiss-before-repeat", "dismiss")
    with pytest.raises(EvidenceError):
        ProfileReflectionService(V4FactMemory(tool_repo)).propose(
            "alice",
            "self",
            [{"section": 5, "text": proposal["text"], "fact_ids": [row["id"]], "item_id": None}],
            fact_versions=proposal["input_fact_versions"],
            operation_id="repeat-dismissed-profile",
        )
    assert tool_repo.get("alice", "proposal", proposal["id"], include_deleted=True)["status"] == "deleted"


def test_corrupted_preparation_time_cannot_authorize_a_profile(tool_repo: Any) -> None:
    proposal, _ = candidate(tool_repo)
    corrupt = tool_repo.update(
        "alice",
        "proposal",
        proposal["id"],
        {"prepared_at": "invalid"},
        expected_revision=proposal["revision"],
    )
    with pytest.raises(EvidenceError):
        action(tool_repo, corrupt, ACCEPT_PROFILE, NOW, "corrupt-preparation")
    assert tool_repo.get("alice", "proposal", proposal["id"]) == corrupt
    assert tool_repo.list("alice", "profile_doc") == []

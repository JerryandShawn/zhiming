"""P3 proposals are confirmed with current user evidence, never model consent flags."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_proposals import SAVE_CATEGORY, SAVE_ONCE, MemoryProposalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import SAID_AT, Harness, setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def proposal_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def pending(repo: PostgresRepository, text: str = "我被诊断出焦虑症了，最近在吃药") -> tuple[Harness, str]:
    h = setup(repo, text)
    result, _, _ = h.write("background")
    assert result.receipt["write_status"] == "pending_confirmation"
    assert h.service.memory.facts("alice") == []
    return h, result.receipt["id"]


def confirm(
    repo: PostgresRepository,
    ident: str,
    *,
    remember: bool = False,
    action: dict[str, Any] | None = None,
    owner: str = "alice",
    subject: str = "self",
    operation: str = "synthetic-confirm",
    revision: int = 1,
) -> dict[str, Any]:
    memory = MemoryService(repo)
    action = action or memory.receive(
        owner,
        subject,
        content=SAVE_CATEGORY if remember else SAVE_ONCE,
        source_id=operation,
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=1),
    )
    return MemoryProposalService(memory).accept(
        owner,
        subject,
        ident,
        expected_revision=revision,
        message_id=action["id"],
        remember_category=remember,
        operation_id=operation,
    )


def test_confirm_once_preserves_actual_original_and_approval_and_replays(tool_repo: PostgresRepository) -> None:
    h, ident = pending(tool_repo)
    receipt = confirm(tool_repo, ident)
    fact = tool_repo.get("alice", "fact", receipt["fact_id"])
    assert fact["content"] == h.source["content"]
    assert fact["source_refs"][0]["message_id"] == h.source["id"] and len(fact["source_refs"]) == 2
    before = tool_repo.get_revision("alice")
    assert confirm(tool_repo, ident) == receipt and tool_repo.get_revision("alice") == before
    assert tool_repo.assert_scope("alice")["settings"].get("auto_save_categories", []) == []
    assert tool_repo.get("alice", "proposal", ident)["status"] == "accepted"


def test_category_confirmation_enables_following_health_but_not_money(tool_repo: PostgresRepository) -> None:
    first, ident = pending(tool_repo)
    confirm(tool_repo, ident, remember=True)
    first.finish()
    second = setup(tool_repo, "我这周复诊了")
    result, _, _ = second.write("background")
    assert result.ok and result.receipt["write_status"] == "saved"
    later = tool_repo.get("alice", "fact", result.receipt["fact_id"])
    assert later["category_consent_ids"] and len(later["source_refs"]) == 3
    assert tool_repo.assert_scope("alice")["settings"]["auto_save_categories"] == ["health"]
    second.finish()
    third = setup(tool_repo, "我现在欠款合成金额200元")
    result, _, _ = third.write("background")
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"


def test_third_party_health_needs_both_categories_and_can_be_confirmed_once(tool_repo: PostgresRepository) -> None:
    h, ident = pending(tool_repo, "我妈今年血压一直很高")
    proposal = tool_repo.get("alice", "proposal", ident)
    assert set(proposal["categories"]) == {"health", "third_party"}
    receipt = confirm(tool_repo, ident)
    assert tool_repo.get("alice", "fact", receipt["fact_id"])["content"] == h.source["content"]
    assert (
        MemoryService(tool_repo).save_fact("alice", "self", h.source["id"], h.source["content"], "background")[
            "write_status"
        ]
        == "pending_confirmation"
    )


@pytest.mark.parametrize("role,content", [("assistant", SAVE_ONCE), ("user", "可以吗？"), ("user", "不要保存这条记忆")])
def test_non_authorizing_actions_leave_proposal_pending(tool_repo: PostgresRepository, role: str, content: str) -> None:
    _, ident = pending(tool_repo)
    action = MemoryService(tool_repo).receive(
        "alice",
        content=content,
        role=role,
        source_id="invalid-action",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=1),
    )
    with pytest.raises(EvidenceError):
        confirm(tool_repo, ident, action=action)
    assert tool_repo.get("alice", "proposal", ident)["status"] == "pending"
    assert tool_repo.list("alice", "fact") == [] and tool_repo.list("alice", "consent") == []


def test_stale_proposal_source_or_revision_cannot_authorize_write(tool_repo: PostgresRepository) -> None:
    h, ident = pending(tool_repo)
    with pytest.raises(RevisionConflict):
        confirm(tool_repo, ident, revision=2)
    tool_repo.update("alice", "message", h.source["id"], {"synthetic_revision": True}, expected_revision=1)
    with pytest.raises(EvidenceError):
        confirm(tool_repo, ident)
    assert tool_repo.list("alice", "fact") == [] and tool_repo.list("alice", "consent") == []


def test_confirmation_cannot_cross_owners(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    with pytest.raises(ScopeError):
        confirm(tool_repo, ident, owner="bob")
    assert tool_repo.list("bob", "fact") == []


def test_revoking_confirmation_disables_future_category_autosave(tool_repo: PostgresRepository) -> None:
    first, ident = pending(tool_repo)
    receipt = confirm(tool_repo, ident, remember=True)
    fact = tool_repo.get("alice", "fact", receipt["fact_id"])
    approval = fact["source_refs"][1]
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(
            connection,
            "alice",
            "source_span",
            "withdrawn-approval",
            "stopped",
            {"message_id": approval["message_id"], "start": approval["start"], "end": approval["end"]},
        )
    first.finish()
    second = setup(tool_repo, "我这周复诊了")
    result, _, _ = second.write("background")
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    with pytest.raises(EvidenceError):
        confirm(tool_repo, ident, remember=True)


def test_one_action_cannot_confirm_two_distinct_proposals(tool_repo: PostgresRepository) -> None:
    first, one = pending(tool_repo)
    first.finish()
    _, two = pending(tool_repo, "我最近失眠，正在吃药")
    action = MemoryService(tool_repo).receive(
        "alice", content=SAVE_ONCE, source_id="single-action", at=SAID_AT + timedelta(minutes=1), channel="synthetic"
    )
    confirm(tool_repo, one, action=action)
    with pytest.raises((EvidenceError, RevisionConflict)):
        confirm(tool_repo, two, action=action, operation="synthetic-other-confirm")
    assert tool_repo.get("alice", "proposal", two)["status"] == "pending"


def test_confirmation_receipts_and_consent_have_no_private_quote(tool_repo: PostgresRepository) -> None:
    h, ident = pending(tool_repo)
    confirm(tool_repo, ident, remember=True)
    with tool_repo.transaction("alice") as connection:
        receipts = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert all(h.source["content"] not in str(row) for row in receipts)
    assert all(h.source["content"] not in str(row) for row in tool_repo.list("alice", "consent"))


def test_reject_purges_proposal_body_and_replays_without_saving(tool_repo: PostgresRepository) -> None:
    h, ident = pending(tool_repo)
    memory = MemoryService(tool_repo)
    action = memory.receive(
        "alice", content="不要保存这条记忆", source_id="reject", channel="synthetic", at=SAID_AT + timedelta(minutes=1)
    )
    service = MemoryProposalService(memory)
    arguments = {"expected_revision": 1, "message_id": action["id"], "operation_id": "reject-once"}
    receipt = service.reject("alice", "self", ident, **arguments)
    deleted = tool_repo.get("alice", "proposal", ident, include_deleted=True)
    assert receipt["write_status"] == "stopped" and deleted["status"] == "deleted"
    assert h.source["content"] not in str(deleted)
    revision = tool_repo.get_revision("alice")
    assert service.reject("alice", "self", ident, **arguments) == receipt
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.list("alice", "fact") == [] and tool_repo.list("alice", "consent") == []
    with pytest.raises(EvidenceError):
        confirm(tool_repo, ident)


@pytest.mark.parametrize("remember,accepted", [(True, True), (False, False)])
def test_short_category_action_is_literal_and_requires_category_intent(
    tool_repo: PostgresRepository, remember: bool, accepted: bool
) -> None:
    _, ident = pending(tool_repo)
    memory = MemoryService(tool_repo)
    action = memory.receive(
        "alice",
        content="以后这类都记",
        channel="web-action",
        source_id="short-category",
        at=SAID_AT + timedelta(minutes=1),
    )
    if accepted:
        receipt = confirm(tool_repo, ident, action=action, remember=remember)
        fact = tool_repo.get("alice", "fact", receipt["fact_id"])
        assert fact["source_refs"][1]["quote"] == "以后这类都记"
        assert tool_repo.assert_scope("alice")["settings"]["auto_save_categories"] == ["health"]
    else:
        with pytest.raises(EvidenceError):
            confirm(tool_repo, ident, action=action, remember=remember)
        assert tool_repo.list("alice", "fact") == []

"""Selected-item privacy actions preserve owner, version, source and replay boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock


@pytest.fixture
def seeded(p2_repo: PostgresRepository) -> Iterator[tuple]:
    previous = get_clock()
    at = datetime.fromisoformat("2026-10-17T10:30:00+08:00")
    set_clock(FrozenClock(at))
    memory = MemoryService(p2_repo)
    source = memory.receive(
        "alice", content="请记住，我不能上夜班", source_id="selected-original", at=at - timedelta(days=1)
    )
    fact = memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    p2_repo.put(
        "alice",
        "note",
        "derived-note",
        {"content": "合成笔记", "fact_ids": [fact["id"]], "source_ids": [source["id"]]},
        expected_revision=0,
    )
    p2_repo.put("bob", "note", "derived-note", {"content": "另一个所有者"}, expected_revision=0)
    try:
        yield memory, source, fact, at
    finally:
        set_clock(previous)


def action(memory: MemoryService, at: datetime, text: str, **kwargs: Any) -> dict:
    return memory.receive("alice", content=text, source_id="selected-command", at=at, **kwargs)


@pytest.mark.parametrize("kind", ["fact", "message"])
def test_selected_deletion_cascades_and_replay_is_read_only(seeded: tuple, kind: str) -> None:
    memory, source, fact, at = seeded
    target = fact if kind == "fact" else source
    command = action(memory, at, "撤销这条记忆" if kind == "fact" else "删除这条来源消息")
    service = MemoryWithdrawalService(memory)
    method = service.withdraw_fact if kind == "fact" else service.delete_source
    args = dict(expected_revision=target["revision"], message_id=command["id"], operation_id="selected-delete")
    receipt = method("alice", "self", target["id"], **args)
    assert receipt["write_status"] == "deleted"
    assert memory.repo.get("alice", "fact", fact["id"], include_deleted=True)["status"] == "deleted"
    assert memory.repo.get("alice", "note", "derived-note", include_deleted=True)["status"] == "deleted"
    assert memory.repo.get("bob", "note", "derived-note")["content"] == "另一个所有者"
    before = memory.repo.get_revision("alice")
    assert method("alice", "self", target["id"], **args) == receipt
    assert memory.repo.get_revision("alice") == before
    if kind == "message":
        assert memory.repo.get("alice", "message", source["id"], include_deleted=True)["status"] == "deleted"
    else:
        assert memory.repo.get("alice", "message", source["id"])["status"] == "active"


@pytest.mark.parametrize("change", ["role", "wording", "old", "future", "version", "owner", "subject"])
def test_unsafe_selected_actions_do_not_delete(seeded: tuple, change: str) -> None:
    memory, source, fact, at = seeded
    text = "删除这条来源消息" if change != "wording" else "我考虑删掉一些东西"
    when = at - timedelta(days=2) if change == "old" else at + timedelta(days=1) if change == "future" else at
    command = action(memory, when, text, role="assistant" if change == "role" else "user")
    with pytest.raises((EvidenceError, RevisionConflict, ScopeError)):
        MemoryWithdrawalService(memory).delete_source(
            "bob" if change == "owner" else "alice",
            "other" if change == "subject" else "self",
            source["id"],
            expected_revision=source["revision"] + int(change == "version"),
            message_id=command["id"],
            operation_id="bad",
        )
    assert memory.repo.get("alice", "message", source["id"])["status"] == "active"
    assert memory.repo.get("alice", "fact", fact["id"])["status"] == "active"


def test_deleting_source_with_no_facts_still_clears_derived_notes(seeded: tuple) -> None:
    memory, _, _, at = seeded
    source = memory.receive("alice", content="仅有原话的合成来源", source_id="source-only", at=at - timedelta(hours=1))
    memory.repo.put("alice", "note", "source-only-note", {"source_ids": [source["id"]]}, expected_revision=0)
    command = action(memory, at, "删除这条来源消息")
    MemoryWithdrawalService(memory).delete_source(
        "alice",
        "self",
        source["id"],
        expected_revision=source["revision"],
        message_id=command["id"],
        operation_id="no-fact-delete",
    )
    assert memory.repo.get("alice", "note", "source-only-note", include_deleted=True)["status"] == "deleted"


def test_selected_button_original_cannot_be_reused_for_another_source(seeded: tuple) -> None:
    memory, source, _, at = seeded
    other = memory.receive("alice", content="另一条合成原话", source_id="other-original", at=at - timedelta(hours=1))
    command = action(memory, at, "删除这条来源消息")
    service = MemoryWithdrawalService(memory)
    service.delete_source(
        "alice",
        "self",
        source["id"],
        expected_revision=source["revision"],
        message_id=command["id"],
        operation_id="one-selected-source",
    )
    with pytest.raises(EvidenceError):
        service.delete_source(
            "alice",
            "self",
            other["id"],
            expected_revision=other["revision"],
            message_id=command["id"],
            operation_id="another-selection",
        )
    assert memory.repo.get("alice", "message", other["id"])["status"] == "active"


def test_changed_confirmation_source_or_private_action_cannot_replay(seeded: tuple) -> None:
    memory, source, fact, at = seeded
    command = action(memory, at, "撤销这条记忆")
    service = MemoryWithdrawalService(memory)
    args = dict(expected_revision=fact["revision"], message_id=command["id"], operation_id="selected-withdraw")
    service.withdraw_fact("alice", "self", fact["id"], **args)
    memory.repo.update(
        "alice",
        "message",
        command["id"],
        {"policy": dict(command["policy"], persist_allowed=False)},
        expected_revision=command["revision"],
    )
    with pytest.raises(EvidenceError):
        service.withdraw_fact("alice", "self", fact["id"], **args)


@pytest.mark.parametrize("callback_fails", [False, True])
def test_source_callback_receives_source_id_and_failure_rolls_back_atomically(
    seeded: tuple, callback_fails: bool
) -> None:
    memory, source, fact, at = seeded
    seen = []

    def callback(owner: str, facts: list[str], sources: list[str]) -> None:
        seen.append((owner, facts, sources))
        if callback_fails and sources:
            raise EvidenceError("合成下游撤销失败")

    memory.on_revoke = callback
    command = action(memory, at, "删除这条来源消息")
    service = MemoryWithdrawalService(memory)
    args = dict(expected_revision=source["revision"], message_id=command["id"], operation_id="callback-withdraw")
    if callback_fails:
        with pytest.raises(EvidenceError):
            service.delete_source("alice", "self", source["id"], **args)
        assert memory.repo.get("alice", "message", source["id"])["status"] == "active"
        assert memory.repo.get("alice", "fact", fact["id"])["status"] == "active"
        assert memory.repo.get("alice", "note", "derived-note")["status"] == "active"
        assert not memory.repo.is_revoked("alice", "message", source["id"])
    else:
        service.delete_source("alice", "self", source["id"], **args)
    assert seen[-1] == ("alice", [fact["id"]], [source["id"]])


@pytest.mark.parametrize("flag", [1, "true", None])
def test_truthy_policy_metadata_does_not_authorize_selected_deletion(seeded: tuple, flag: object) -> None:
    memory, source, _, at = seeded
    command = action(memory, at, "删除这条来源消息")
    memory.repo.update(
        "alice",
        "message",
        command["id"],
        {"policy": dict(command["policy"], run_context=flag)},
        expected_revision=command["revision"],
    )
    with pytest.raises(EvidenceError):
        MemoryWithdrawalService(memory).delete_source(
            "alice",
            "self",
            source["id"],
            expected_revision=source["revision"],
            message_id=command["id"],
            operation_id="truthy-flag",
        )
    assert memory.repo.get("alice", "message", source["id"])["status"] == "active"

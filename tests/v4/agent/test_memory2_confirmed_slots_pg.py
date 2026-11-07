"""Combined real P3 consent and slot changes undo atomically, including their dependent grants."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_confirmed_slots import MemoryConfirmedSlotService
from mingjing_core.application.memory2_confirmed_slots_undo import UNDO_CONFIRMED_SLOT, MemoryConfirmedSlotUndoService
from mingjing_core.application.memory2_proposals import SAVE_CATEGORY, SAVE_ONCE
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError

from .test_memory2_proposal_undo_pg import business
from .test_memory2_slots_pg import fact, slots_repo
from .test_toolkit_pg import SAID_AT, setup


@pytest.fixture(name="tool_repo")
def confirmed_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return slots_repo.__wrapped__(p2_repo, monkeypatch)


def prepared(repo: Any, *, remember: bool = False) -> dict:
    old = fact(repo, "我习惯早睡早起", "2026-10-16T10:00:00+08:00", slot="sleep_schedule")
    h = setup(repo, "我最近失眠，改为晚睡")
    result, _, _ = h.write("background")
    assert result.receipt["write_status"] == "pending_confirmation"
    proposal = repo.get("alice", "proposal", result.receipt["id"])
    action = h.service.memory.receive(
        "alice",
        content=SAVE_CATEGORY if remember else SAVE_ONCE,
        source_id="combined-approve",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=1),
    )
    h.finish()
    return dict(
        old=old,
        proposal=proposal,
        action=action,
        remember=remember,
        settings=repo.assert_scope("alice")["settings"],
        memory=V4FactMemory(repo),
    )


def accept(state: dict, **changes: Any) -> dict:
    args = dict(
        slot="sleep_schedule",
        expected_proposal_revision=state["proposal"]["revision"],
        expected_old_revision=state["old"]["revision"],
        message_id=state["action"]["id"],
        remember_category=state["remember"],
        operation_id="combined-accept",
    )
    args.update(changes)
    return MemoryConfirmedSlotService(state["memory"]).accept(
        "alice",
        "self",
        state["proposal"]["id"],
        state["old"]["id"],
        **args,
    )


def undo(state: dict, receipt: dict, *, command: str = UNDO_CONFIRMED_SLOT, **changes: Any) -> dict:
    action = state["memory"].receive(
        "alice",
        content=command,
        source_id="combined-undo",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=3),
    )
    args = dict(expected_revision=receipt["context_revision"], message_id=action["id"], operation_id="combined-undo")
    args.update(changes)
    return MemoryConfirmedSlotUndoService(state["memory"]).undo("alice", "self", receipt["ids"][0], **args)


@pytest.mark.parametrize("remember", [False, True])
def test_atomic_confirmation_replacement_and_undo_restore_exact_old_fields_and_pending(tool_repo: Any, remember: bool):
    state = prepared(tool_repo, remember=remember)
    receipt = accept(state)
    assert [r["id"] for r in state["memory"].facts("alice")] == [receipt["fact_id"]]
    assert accept(state) == receipt
    tool_repo.put("alice", "note", "combined-derived", {"fact_ids": [receipt["fact_id"]]}, expected_revision=0)
    restored = undo(state, receipt)
    assert business(tool_repo.get("alice", "fact", state["old"]["id"])) == business(state["old"])
    assert business(tool_repo.get("alice", "proposal", state["proposal"]["id"])) == business(state["proposal"])
    assert tool_repo.assert_scope("alice")["settings"] == state["settings"]
    assert tool_repo.get("alice", "note", "combined-derived", include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)["status"] == "deleted"
    assert [r["id"] for r in state["memory"].facts("alice")] == [state["old"]["id"]]
    assert tool_repo.get("alice", "consent", restored["ids"][2], include_deleted=True)["status"] == "deleted"
    revision = tool_repo.get_revision("alice")
    assert undo(state, receipt) == restored and tool_repo.get_revision("alice") == revision
    with pytest.raises(EvidenceError):
        accept(state)


def test_later_category_fact_and_its_claim_are_retired_with_confirmation(tool_repo: Any):
    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    later = setup(tool_repo, "我最近失眠，已经开始复诊")
    saved, _, _ = later.write("background")
    assert saved.ok and saved.receipt["write_status"] == "saved"
    later.finish()
    tool_repo.put("alice", "note", "later-health", {"fact_ids": [saved.receipt["fact_id"]]}, expected_revision=0)
    restored = undo(state, receipt)
    assert saved.receipt["fact_id"] in restored["affected_ids"]
    assert tool_repo.get("alice", "fact", saved.receipt["fact_id"])["status"] == "retired"
    assert tool_repo.get("alice", "note", "later-health", include_deleted=True)["status"] == "deleted"
    assert [r["id"] for r in state["memory"].facts("alice")] == [state["old"]["id"]]


@pytest.mark.parametrize("error", ["slot", "revision", "source"])
def test_failed_replacement_rolls_back_confirmation_fact_consent_settings_and_all_revisions(tool_repo: Any, error: str):
    state = prepared(tool_repo, remember=True)
    changes = {}
    if error == "slot":
        changes["slot"] = "employer"
    elif error == "revision":
        changes["expected_old_revision"] = state["old"]["revision"] + 1
    else:
        source = state["memory"].get_source("alice", state["proposal"]["source_refs"][0]["message_id"])
        tool_repo.update(
            "alice", "message", source["id"], {"synthetic_edit": True}, expected_revision=source["revision"]
        )
    revision = tool_repo.get_revision("alice")
    with pytest.raises((EvidenceError, RevisionConflict)):
        accept(state, **changes)
    assert tool_repo.get_revision("alice") == revision
    assert business(tool_repo.get("alice", "proposal", state["proposal"]["id"])) == business(state["proposal"])
    assert tool_repo.list("alice", "consent") == []
    assert tool_repo.assert_scope("alice")["settings"] == state["settings"]
    assert [r["id"] for r in tool_repo.list("alice", "fact")] == [state["old"]["id"]]


def test_later_edit_rejects_undo_without_restoring_settings_or_pending(tool_repo: Any):
    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    tool_repo.update(
        "alice", "fact", receipt["fact_id"], {"summary": "合成后续修改"}, expected_revision=receipt["revision"]
    )
    settings = tool_repo.assert_scope("alice")["settings"]
    with pytest.raises(EvidenceError):
        undo(state, receipt)
    assert tool_repo.assert_scope("alice")["settings"] == settings
    assert tool_repo.get("alice", "proposal", state["proposal"]["id"])["status"] == "accepted"
    assert tool_repo.get("alice", "fact", state["old"]["id"])["superseded_by"] == receipt["fact_id"]


@pytest.mark.parametrize("withdrawn", ["original", "approval", "old_fact"])
def test_withdrawn_original_approval_or_old_fact_can_never_be_revived(tool_repo: Any, withdrawn: str):
    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    if withdrawn == "old_fact":
        row = tool_repo.get("alice", "fact", state["old"]["id"])
        state["memory"].retire_fact("alice", row["id"], expected_revision=row["revision"])
    else:
        ident = state["proposal"]["source_refs"][0]["message_id"] if withdrawn == "original" else state["action"]["id"]
        row = tool_repo.get("alice", "message", ident)
        SourceWithdrawalService(state["memory"]).delete(
            "alice", "self", ident, expected_revision=row["revision"], request_id="combined-source-withdraw"
        )
    with pytest.raises((EvidenceError, RevisionConflict)):
        undo(state, receipt)
    assert tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)["status"] == "deleted"


def test_plain_slot_undo_command_cannot_also_revoke_sensitive_confirmation(tool_repo: Any):
    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    with pytest.raises(EvidenceError):
        undo(state, receipt, command="撤销这次记忆更新")
    assert tool_repo.get("alice", "fact", receipt["fact_id"])["status"] == "active"


def test_other_owner_cannot_consume_or_undo_combined_change(tool_repo: Any):
    state = prepared(tool_repo)
    receipt = accept(state)
    with pytest.raises(ScopeError):
        MemoryConfirmedSlotUndoService(state["memory"]).undo(
            "bob",
            "self",
            receipt["ids"][0],
            expected_revision=receipt["context_revision"],
            message_id=state["action"]["id"],
            operation_id="other-owner",
        )


def test_new_category_grant_cannot_launder_an_old_unapproved_sensitive_fact(tool_repo: Any):
    state = prepared(tool_repo, remember=True)
    source = state["memory"].receive(
        "alice",
        content="我一直失眠，习惯早睡",
        source_id="legacy-unsafe",
        channel="synthetic",
        at="2026-10-15T10:00:00+08:00",
    )
    raw = state["memory"].save_fact("alice", "self", source["id"], source["content"], "preference")
    assert raw["write_status"] == "saved"
    state["old"] = tool_repo.update(
        "alice", "fact", raw["id"], {"slot": "sleep_schedule"}, expected_revision=raw["revision"]
    )
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError, match="敏感记忆"):
        accept(state)
    assert tool_repo.get_revision("alice") == revision and tool_repo.list("alice", "consent") == []


def test_failure_during_invalidation_rolls_back_old_value_pending_and_grants(tool_repo: Any, monkeypatch):
    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    old = tool_repo.get("alice", "fact", state["old"]["id"])
    new = tool_repo.get("alice", "fact", receipt["fact_id"])
    settings = tool_repo.assert_scope("alice")["settings"]
    action = state["memory"].receive(
        "alice",
        content=UNDO_CONFIRMED_SLOT,
        source_id="rollback-undo",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=3),
    )
    revision = tool_repo.get_revision("alice")

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic invalidation failure")

    monkeypatch.setattr(tool_repo, "invalidate_derived", fail)
    with pytest.raises(RuntimeError, match="synthetic invalidation failure"):
        MemoryConfirmedSlotUndoService(state["memory"]).undo(
            "alice",
            "self",
            receipt["ids"][0],
            expected_revision=receipt["context_revision"],
            message_id=action["id"],
            operation_id="rollback-undo",
        )
    # The entire failing undo, including its action binding, rolls back.
    assert business(tool_repo.get("alice", "fact", old["id"])) == business(old)
    assert business(tool_repo.get("alice", "fact", new["id"])) == business(new)
    assert tool_repo.assert_scope("alice")["settings"] == settings
    assert tool_repo.get("alice", "proposal", state["proposal"]["id"])["status"] == "accepted"
    assert tool_repo.get_revision("alice") == revision


@pytest.mark.parametrize("changed", ["pending", "restored_fact", "approval_source"])
def test_cached_undo_cannot_be_reused_after_result_authority_changes(tool_repo: Any, changed: str):
    state = prepared(tool_repo)
    receipt = accept(state)
    restored = undo(state, receipt)
    if changed == "pending":
        row = tool_repo.get("alice", "proposal", restored["ids"][1])
        tool_repo.update("alice", "proposal", row["id"], {"summary": "合成后来修改"}, expected_revision=row["revision"])
    elif changed == "restored_fact":
        row = tool_repo.get("alice", "fact", restored["fact_id"])
        state["memory"].retire_fact("alice", row["id"], expected_revision=row["revision"])
    else:
        row = tool_repo.get("alice", "message", state["action"]["id"])
        SourceWithdrawalService(state["memory"]).delete(
            "alice", "self", row["id"], expected_revision=row["revision"], request_id="after-undo-withdraw"
        )
    with pytest.raises(EvidenceError):
        undo(state, receipt)


def test_undo_of_unrelated_proposal_is_rejected_as_a_domain_error(tool_repo: Any):
    state = prepared(tool_repo)
    receipt = accept(state)
    invalid = dict(receipt, ids=[state["proposal"]["id"]], context_revision=2)
    with pytest.raises(EvidenceError):
        undo(state, invalid)


def test_undo_command_created_before_the_change_does_not_authorize_a_later_change(tool_repo: Any):
    state = prepared(tool_repo)
    early = state["memory"].receive(
        "alice",
        content=UNDO_CONFIRMED_SLOT,
        source_id="early-undo",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=3),
    )
    receipt = accept(state)
    with pytest.raises(EvidenceError):
        MemoryConfirmedSlotUndoService(state["memory"]).undo(
            "alice",
            "self",
            receipt["ids"][0],
            expected_revision=receipt["context_revision"],
            message_id=early["id"],
            operation_id="too-early",
        )
    assert tool_repo.get("alice", "fact", receipt["fact_id"])["status"] == "active"


def test_same_undo_action_cannot_bind_a_different_operation(tool_repo: Any):
    state = prepared(tool_repo)
    receipt = accept(state)
    undo(state, receipt)
    with pytest.raises(EvidenceError, match="intent"):
        undo(state, receipt, operation_id="another-operation")


def test_undo_action_from_another_thread_is_not_long_term_authority(tool_repo: Any):
    state = prepared(tool_repo)
    receipt = accept(state)
    source = state["memory"].receive(
        "alice",
        content=UNDO_CONFIRMED_SLOT,
        source_id="wrong-thread",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=3),
    )
    source = tool_repo.update(
        "alice", "message", source["id"], {"thread_id": "other-thread"}, expected_revision=source["revision"]
    )
    with pytest.raises(EvidenceError):
        undo(state, receipt, message_id=source["id"])


def test_unrelated_owner_settings_survive_combined_undo(tool_repo: Any):
    from psycopg import sql
    from psycopg.types.json import Jsonb

    state = prepared(tool_repo, remember=True)
    receipt = accept(state)
    settings = dict(tool_repo.assert_scope("alice")["settings"], synthetic_unrelated="keep")
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(tool_repo.table("core_owners")),
            (Jsonb(settings), "alice"),
        )
    undo(state, receipt)
    assert tool_repo.assert_scope("alice")["settings"] == dict(state["settings"], synthetic_unrelated="keep")


def test_future_confirmation_cannot_grant_a_category_or_replace_a_slot(tool_repo: Any):
    state = prepared(tool_repo, remember=True)
    future = state["memory"].receive(
        "alice", content=SAVE_CATEGORY, source_id="future-confirm", channel="synthetic", at="2027-01-01T10:00:00+08:00"
    )
    with pytest.raises(EvidenceError):
        accept(state, message_id=future["id"])
    assert tool_repo.assert_scope("alice")["settings"] == state["settings"]
    assert tool_repo.list("alice", "consent") == []

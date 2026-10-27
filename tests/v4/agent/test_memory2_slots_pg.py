"""Real single-slot update and undo services preserve authorization and historical validity."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import pytest

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.application.memory2_slots import MemorySlotUpdateService
from mingjing_core.application.memory2_slots_undo import MemorySlotUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.timekit.clock import FrozenClock

from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as base_tool_repo

SINGLE_EXAMPLES = [
    ("residence_city", "我现在住在杭州", "我搬到上海了"),
    ("employer", "我入职了合成甲公司", "我入职了合成乙公司"),
    ("job_role", "我的岗位是合成教师", "我转岗做合成设计师"),
    ("relationship_status", "我现在单身", "我结婚了"),
    ("spice_preference", "我不吃辣", "我最近能吃点辣了"),
    ("sleep_schedule", "我习惯早睡早起", "我现在改为晚睡"),
    ("exam_goal", "我准备考合成甲证", "我准备考合成乙证"),
    ("preferred_name", "以后叫我合成甲", "现在叫我合成乙"),
]


@pytest.fixture(name="tool_repo")
def slots_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    clock = FrozenClock(datetime.fromisoformat("2026-10-24T00:00:00+08:00"))
    monkeypatch.setattr("mingjing_core.timekit.clock._clock", clock)
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def fact(repo: Any, text: str, at: str, *, slot: str | None = None, **metadata: Any) -> dict:
    memory = V4FactMemory(repo)
    source = memory.receive("alice", content=text, source_id=uuid.uuid4().hex, channel="synthetic", at=at)
    result = memory.save_fact("alice", "self", source["id"], text, "background")
    assert result["write_status"] == "saved"
    return repo.update(
        "alice", "fact", result["id"], {"slot": slot, "said_at": at, **metadata}, expected_revision=result["revision"]
    )


def pair(
    repo: Any, slot: str = "residence_city", old_text: str = "我现在住在杭州", new_text: str = "我搬到上海了"
) -> tuple[dict, dict]:
    old = fact(repo, old_text, "2026-10-17T10:00:00+08:00", slot=slot)
    new = fact(repo, new_text, "2026-10-18T10:00:00+08:00")
    return old, new


def update(repo: Any, old: dict, new: dict, **changes: Any) -> dict:
    return MemorySlotUpdateService(V4FactMemory(repo)).update(
        "alice",
        "self",
        old["id"],
        new["id"],
        **{
            "slot": old["slot"],
            "expected_old_revision": old["revision"],
            "expected_new_revision": new["revision"],
            "operation_id": "synthetic-slot-update",
            **changes,
        },
    )


def undo(repo: Any, receipt: dict, **changes: Any) -> dict:
    memory = V4FactMemory(repo)
    action = memory.receive("alice", content="撤销这次记忆更新", source_id="synthetic-slot-undo", channel="synthetic")
    return MemorySlotUndoService(memory).undo(
        "alice",
        "self",
        receipt["ids"][0],
        **{"expected_revision": 1, "message_id": action["id"], "operation_id": "synthetic-slot-undo", **changes},
    )


@pytest.mark.parametrize("slot,old_text,new_text", SINGLE_EXAMPLES)
def test_each_single_slot_updates_current_value_but_preserves_old_history(
    tool_repo: Any, slot: str, old_text: str, new_text: str
) -> None:
    old, new = pair(tool_repo, slot, old_text, new_text)
    receipt = update(tool_repo, old, new)
    previous = tool_repo.get("alice", "fact", old["id"])
    current = tool_repo.get("alice", "fact", new["id"])
    assert receipt["write_status"] == "updated" and receipt["fact_id"] == new["id"]
    assert previous["status"] == "active" and previous["valid_to"] == "2026-10-18T02:00:00+00:00"
    assert previous["superseded_by"] == new["id"] and current["supersedes"] == old["id"]
    assert current["valid_from"] == previous["valid_to"] and current["slot"] == slot
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [new["id"]]
    revision = tool_repo.get_revision("alice")
    assert update(tool_repo, old, new) == receipt
    assert tool_repo.get_revision("alice") == revision


def test_undo_restores_exact_old_fields_and_invalidates_new_value_claims(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    receipt = update(tool_repo, old, new)
    tool_repo.put("alice", "note", "synthetic-new-claim", {"fact_ids": [new["id"]]}, expected_revision=0)
    restored_receipt = undo(tool_repo, receipt)
    restored = tool_repo.get("alice", "fact", old["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in restored.items() if k not in reserved} == {
        k: v for k, v in old.items() if k not in reserved
    }
    assert tool_repo.get("alice", "fact", new["id"])["status"] == "retired"
    assert tool_repo.get("alice", "note", "synthetic-new-claim", include_deleted=True)["status"] == "deleted"
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [old["id"]]
    revision = tool_repo.get_revision("alice")
    assert undo(tool_repo, receipt) == restored_receipt
    assert tool_repo.get_revision("alice") == revision
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new)


@pytest.mark.parametrize(
    "metadata", [{"said_at": "2026-10-16T00:00:00+08:00"}, {"consent": "pending"}, {"slot": "employer"}]
)
def test_untrusted_metadata_or_unapproved_facts_do_not_change_old_slot(tool_repo: Any, metadata: dict) -> None:
    old, new = pair(tool_repo)
    new = tool_repo.update("alice", "fact", new["id"], metadata, expected_revision=new["revision"])
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new)
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", old["id"]).get("valid_to") is None


@pytest.mark.parametrize("slot", ["hobbies", "not_a_slot"])
def test_multi_or_unknown_slot_cannot_be_updated(tool_repo: Any, slot: str) -> None:
    old, new = pair(tool_repo)
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new, slot=slot)


def test_temporary_fact_admission_and_slot_update_can_rollback_together(tool_repo: Any) -> None:
    old = fact(tool_repo, "我住在杭州", "2026-10-17T10:00:00+08:00", slot="residence_city")
    with pytest.raises(EvidenceError), tool_repo.transaction("alice"):
        new = fact(tool_repo, "我在上海出差一周", "2026-10-18T10:00:00+08:00")
        update(tool_repo, old, new)
    assert [row["id"] for row in tool_repo.list("alice", "fact")] == [old["id"]]


def test_revision_source_owner_and_subject_checks(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    with pytest.raises(RevisionConflict):
        update(tool_repo, old, new, expected_old_revision=1)
    service = MemorySlotUpdateService(V4FactMemory(tool_repo))
    with pytest.raises(ScopeError):
        service.update(
            "bob",
            "self",
            old["id"],
            new["id"],
            slot="residence_city",
            expected_old_revision=2,
            expected_new_revision=2,
            operation_id="cross-owner",
        )
    source = tool_repo.get("alice", "message", new["source_refs"][0]["message_id"])
    tool_repo.update(
        "alice", "message", source["id"], {"synthetic_revision": True}, expected_revision=source["revision"]
    )
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new)


def test_undo_rejects_later_edits_and_new_fact_withdrawal(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    receipt = update(tool_repo, old, new)
    tool_repo.update("alice", "fact", new["id"], {"summary": "合成手动修改"}, expected_revision=receipt["revision"])
    with pytest.raises(RevisionConflict):
        undo(tool_repo, receipt)
    current = tool_repo.get("alice", "fact", new["id"])
    V4FactMemory(tool_repo).retire_fact("alice", new["id"], expected_revision=current["revision"])
    change = tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)
    assert change["status"] == "deleted" and "old_before" not in change
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt)


@pytest.mark.parametrize("at", ["2026-10-16T10:00:00+08:00", "2026-10-17T10:00:00+08:00", "2026-11-01T10:00:00+08:00"])
def test_source_chronology_is_strict_and_ignores_host_clock(tool_repo: Any, at: str) -> None:
    old = fact(tool_repo, "我住在杭州", "2026-10-17T10:00:00+08:00", slot="residence_city")
    new = fact(tool_repo, "我搬到上海了", at)
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new)
    assert tool_repo.get("alice", "fact", old["id"]).get("valid_to") is None


def test_multiple_current_values_require_confirmation(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    fact(tool_repo, "我住在合成第三城", "2026-10-17T11:00:00+08:00", slot="residence_city")
    with pytest.raises(EvidenceError, match="多个候选"):
        update(tool_repo, old, new)


def test_update_chain_can_extend_and_latest_undo_keeps_prior_link(tool_repo: Any) -> None:
    first, second = pair(tool_repo)
    update(tool_repo, first, second)
    middle = tool_repo.get("alice", "fact", second["id"])
    third = fact(tool_repo, "我搬到合成第三城了", "2026-10-19T10:00:00+08:00")
    latest = update(tool_repo, middle, third, operation_id="synthetic-second-update")
    undo(tool_repo, latest)
    restored = tool_repo.get("alice", "fact", middle["id"])
    assert restored["supersedes"] == first["id"] and restored.get("superseded_by") is None
    assert tool_repo.get("alice", "fact", first["id"])["superseded_by"] == restored["id"]
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [restored["id"]]


def test_revoked_confirmation_cannot_be_reused_for_update(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    proof = tool_repo.put("alice", "consent", "synthetic-slot-proof", {"status": "stopped"}, expected_revision=0)
    new = tool_repo.update(
        "alice", "fact", new["id"], {"approval_consent_id": proof["id"]}, expected_revision=new["revision"]
    )
    with pytest.raises(EvidenceError):
        update(tool_repo, old, new)


def test_user_undo_action_is_required_and_cached_undo_rechecks_authority(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    receipt = update(tool_repo, old, new)
    memory = V4FactMemory(tool_repo)
    action = memory.receive(
        "alice",
        content="撤销这次记忆更新",
        role="assistant",
        source_id="synthetic-false-slot-undo",
        channel="synthetic",
    )
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt, message_id=action["id"])
    restored = undo(tool_repo, receipt)
    memory.retire_fact("alice", old["id"], expected_revision=restored["revision"])
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt)


def test_sensitive_quote_cannot_hide_behind_low_sensitivity_kind(tool_repo: Any) -> None:
    old = fact(tool_repo, "我习惯早睡早起", "2026-10-17T10:00:00+08:00", slot="sleep_schedule")
    memory = V4FactMemory(tool_repo)
    text = "我最近失眠，改为晚睡"
    source = memory.receive(
        "alice",
        content=text,
        source_id="synthetic-sensitive-preference",
        channel="synthetic",
        at="2026-10-18T10:00:00+08:00",
    )
    # The legacy primitive admits low-sensitivity preference kinds. The real v4
    # tool already checks categories; the new transformation must do so too.
    result = memory.save_fact("alice", "self", source["id"], text, "preference")
    assert result["write_status"] == "saved"
    with pytest.raises(EvidenceError, match="敏感记忆"):
        update(tool_repo, old, tool_repo.get("alice", "fact", result["id"]))
    assert tool_repo.get("alice", "fact", old["id"]).get("valid_to") is None


def test_sensitive_update_reuses_real_p3_proposal_acceptance(tool_repo: Any) -> None:
    old = fact(tool_repo, "我习惯早睡早起", "2026-10-17T10:00:00+08:00", slot="sleep_schedule")
    h = setup(tool_repo, "我最近失眠，改为晚睡")
    pending, _, _ = h.write("background")
    assert pending.receipt["write_status"] == "pending_confirmation"
    action = h.service.memory.receive(
        "alice", content="请保存这条记忆", source_id="synthetic-sensitive-slot-confirm", channel="synthetic"
    )
    accepted = MemoryProposalService(h.service.memory).accept(
        "alice",
        "self",
        pending.receipt["id"],
        expected_revision=pending.receipt["revision"],
        message_id=action["id"],
        remember_category=False,
        operation_id="synthetic-sensitive-slot-accept",
    )
    h.finish()
    new = tool_repo.get("alice", "fact", accepted["fact_id"])
    receipt = update(tool_repo, old, new)
    assert receipt["write_status"] == "updated"
    assert [row["id"] for row in V4FactMemory(tool_repo).facts("alice")] == [new["id"]]


def test_subject_and_case_cannot_be_crossed_by_update(tool_repo: Any) -> None:
    old, new = pair(tool_repo)
    tool_repo.create_subject("alice", "synthetic-other", "合成人物")
    service = MemorySlotUpdateService(V4FactMemory(tool_repo))
    with pytest.raises(ScopeError):
        service.update(
            "alice",
            "synthetic-other",
            old["id"],
            new["id"],
            slot="residence_city",
            expected_old_revision=old["revision"],
            expected_new_revision=new["revision"],
            operation_id="cross-subject",
        )
    memory = V4FactMemory(tool_repo)
    case = memory.create_case("alice", "self", "合成事项", operation_id="synthetic-slot-case")
    source = memory.get_source("alice", new["source_refs"][0]["message_id"])
    memory.receive(
        "alice",
        content=source["content"],
        source_id=source["source_id"],
        channel="synthetic",
        case_ids=[case["id"]],
    )
    new = memory.save_fact("alice", "self", source["id"], source["content"], "background", case_id=case["id"])
    assert new["case_id"] == case["id"]
    with pytest.raises(ScopeError):
        update(tool_repo, old, new)
    assert tool_repo.get("alice", "fact", old["id"]).get("valid_to") is None

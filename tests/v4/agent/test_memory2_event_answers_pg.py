"""Date answers and their undo use real gaps, source messages, facts and native context."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from mingjing_core.application.memory2_event_answers import MemoryEventAnswerService
from mingjing_core.application.memory2_event_answers_undo import UNDO_DATE_ANSWER, MemoryEventAnswerUndoService
from mingjing_core.application.memory2_event_dates_undo import UNDO_EVENT_DATE, MemoryEventTimeUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_context_pg import build
from .test_memory2_event_dates_pg import NOW, legacy_event, repair
from .test_memory2_event_dates_pg import event_date_repo as base_event_repo


@pytest.fixture(name="tool_repo")
def answer_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from base_event_repo.__wrapped__(p2_repo, monkeypatch)


def pending(repo: PostgresRepository) -> tuple[Any, dict, dict]:
    harness, fact = legacy_event(repo, "我最近参加合成面试")
    receipt = repair(harness, fact)
    return harness, fact, receipt


def answer(harness: Any, pending: dict, text: str = "2026-10-18", **changes: Any) -> dict:
    message_id = changes.pop("message_id", None)
    if message_id is None:
        action = harness.service.memory.receive("alice", content=text, source_id="date-answer", at=NOW)
        message_id = action["id"]
    return MemoryEventAnswerService(harness.service.memory, clock=FrozenClock(NOW)).confirm(
        "alice",
        "self",
        pending["id"],
        **{
            "expected_revision": pending["context_revision"],
            "message_id": message_id,
            "operation_id": "date-answer",
            **changes,
        },
    )


def undo(harness: Any, receipt: dict, **changes: Any) -> dict:
    message_id = changes.pop("message_id", None)
    if message_id is None:
        action = harness.service.memory.receive("alice", content=UNDO_DATE_ANSWER, source_id="undo-answer", at=NOW)
        message_id = action["id"]
    return MemoryEventAnswerUndoService(harness.service.memory, clock=FrozenClock(NOW)).undo(
        "alice",
        "self",
        receipt["ids"][0],
        **{
            "expected_revision": receipt["context_revision"],
            "message_id": message_id,
            "operation_id": "undo-answer",
            **changes,
        },
    )


def test_answer_preserves_original_instant_adds_answer_evidence_and_closes_l3_gap(
    tool_repo: PostgresRepository,
) -> None:
    harness, before, gap = pending(tool_repo)
    receipt = answer(harness, gap)
    fact = tool_repo.get("alice", "fact", before["id"])
    assert fact["event_at"] == "2026-10-18" and fact["said_at"] == before["said_at"]
    assert fact["content"] == before["content"] and len(fact["source_refs"]) == 2
    assert fact["source_refs"][0] == before["source_refs"][0]
    assert fact["source_refs"][1]["message_id"] == fact["date_confirmation_message_id"]
    assert tool_repo.get("alice", "knowledge_gap", gap["id"])["status"] == "resolved"
    revision = tool_repo.get_revision("alice")
    assert answer(harness, gap) == receipt
    assert tool_repo.get_revision("alice") == revision
    query = harness.service.memory.receive("alice", content="合成后续问题", source_id="resolved-gap-query")
    result = build(harness.service.memory, query)
    assert gap["id"] not in {row["id"] for row in result.alias_map.values()}


def test_relative_answer_uses_answer_clock_instead_of_original_clock(tool_repo: PostgresRepository) -> None:
    harness, before, gap = pending(tool_repo)
    receipt = answer(harness, gap, "这件事发生在昨天。")
    fact = tool_repo.get("alice", "fact", receipt["fact_id"])
    assert fact["event_at"] == "2026-10-31" and fact["said_at"] == before["said_at"]
    assert fact["date_confirmation_expression"] == "昨天"


def test_exact_undo_reopens_same_gap_and_allows_fresh_answer(tool_repo: PostgresRepository) -> None:
    harness, before, pending_receipt = pending(tool_repo)
    gap_before = tool_repo.get("alice", "knowledge_gap", pending_receipt["id"])
    receipt = answer(harness, pending_receipt)
    tool_repo.put(
        "alice", "note", "answer-derived", {"fact_ids": [before["id"]], "summary": "合成日期派生"}, expected_revision=0
    )
    restored_receipt = undo(harness, receipt)
    restored = tool_repo.get("alice", "fact", before["id"])
    gap = tool_repo.get("alice", "knowledge_gap", pending_receipt["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in restored.items() if k not in reserved} == {
        k: v for k, v in before.items() if k not in reserved
    }
    gap_reserved = reserved | {"target_revision"}
    assert {k: v for k, v in gap.items() if k not in gap_reserved} == {
        k: v for k, v in gap_before.items() if k not in gap_reserved
    }
    assert gap["target_revision"] == restored["revision"]
    assert tool_repo.get("alice", "note", "answer-derived", include_deleted=True)["status"] == "deleted"
    revision = tool_repo.get_revision("alice")
    assert undo(harness, receipt) == restored_receipt
    assert tool_repo.get_revision("alice") == revision
    query = harness.service.memory.receive("alice", content="合成恢复问题", source_id="reopened-gap-query")
    assert gap["id"] in {row["id"] for row in build(harness.service.memory, query).alias_map.values()}
    action = harness.service.memory.receive("alice", content="2026-10-19", source_id="new-date-answer", at=NOW)
    again = answer(
        harness,
        {"id": gap["id"], "context_revision": gap["revision"]},
        message_id=action["id"],
        operation_id="fresh-date-answer",
    )
    assert tool_repo.get("alice", "fact", again["fact_id"])["event_at"] == "2026-10-19"
    with pytest.raises(EvidenceError):
        undo(harness, receipt)


@pytest.mark.parametrize(
    "text",
    [
        "这周",
        "最近",
        "我不知道",
        "如果是明天",
        "2026-10-18？",
        "不要保存，2026-10-18",
        "“2026-10-18”",
        "另一件事发生在2026-10-18",
    ],
)
def test_nonassertive_ambiguous_and_unrelated_answers_do_not_change_gap(
    tool_repo: PostgresRepository, text: str
) -> None:
    harness, before, gap = pending(tool_repo)
    action = harness.service.memory.receive("alice", content=text, source_id="invalid-answer", at=NOW)
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        answer(harness, gap, message_id=action["id"])
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", before["id"]) == before
    assert tool_repo.get("alice", "knowledge_gap", gap["id"])["status"] == "open"


@pytest.mark.parametrize("mode", ["early", "future", "assistant", "incognito", "thread"])
def test_answer_requires_current_original_user_authority(tool_repo: PostgresRepository, mode: str) -> None:
    harness, before = legacy_event(tool_repo, "我最近参加合成面试")
    early = harness.service.memory.receive("alice", content="2026-10-18", source_id="early-answer", at=NOW)
    gap = repair(harness, before)
    at = datetime.fromisoformat("2027-01-01T00:00:00+08:00") if mode == "future" else NOW
    action = (
        early
        if mode == "early"
        else harness.service.memory.receive(
            "alice",
            content="2026-10-18",
            source_id="bad-answer",
            at=at,
            role="assistant" if mode == "assistant" else "user",
        )
    )
    if mode in {"incognito", "thread"}:
        action = tool_repo.update(
            "alice",
            "message",
            action["id"],
            {"incognito": True} if mode == "incognito" else {"thread_id": "other"},
            expected_revision=action["revision"],
        )
    with pytest.raises(EvidenceError):
        answer(harness, gap, message_id=action["id"])


def test_answer_revision_owner_and_later_fact_edit_guards(tool_repo: PostgresRepository) -> None:
    harness, before, gap = pending(tool_repo)
    with pytest.raises(RevisionConflict):
        answer(harness, gap, expected_revision=999)
    service = MemoryEventAnswerService(harness.service.memory, clock=FrozenClock(NOW))
    with pytest.raises(ScopeError):
        service.confirm(
            "bob", "self", gap["id"], expected_revision=1, message_id=harness.source["id"], operation_id="foreign"
        )
    receipt = answer(harness, gap)
    tool_repo.update("alice", "fact", before["id"], {"summary": "合成后改"}, expected_revision=receipt["revision"])
    with pytest.raises(EvidenceError):
        answer(harness, gap)
    with pytest.raises(EvidenceError):
        undo(harness, receipt)


@pytest.mark.parametrize("which", ["original", "answer", "fact"])
def test_withdrawn_confirmation_sources_cannot_be_replayed_or_undone(tool_repo: PostgresRepository, which: str) -> None:
    harness, before, gap = pending(tool_repo)
    receipt = answer(harness, gap)
    fact = tool_repo.get("alice", "fact", before["id"])
    if which == "fact":
        harness.service.memory.retire_fact("alice", before["id"], expected_revision=fact["revision"])
    else:
        ident = harness.source["id"] if which == "original" else fact["date_confirmation_message_id"]
        source = tool_repo.get("alice", "message", ident)
        tool_repo.delete("alice", "message", ident, expected_revision=source["revision"])
    with pytest.raises((EvidenceError, ScopeError)):
        answer(harness, gap)
    with pytest.raises((EvidenceError, ScopeError)):
        undo(harness, receipt)


def test_failed_undo_cascade_is_atomic_and_reopened_gap_keeps_privacy_dependencies(
    tool_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, before, gap = pending(tool_repo)
    receipt = answer(harness, gap)
    action = harness.service.memory.receive("alice", content=UNDO_DATE_ANSWER, source_id="atomic-answer-undo", at=NOW)
    revision = tool_repo.get_revision("alice")

    def failure(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("合成派生清理失败")

    with monkeypatch.context() as patch:
        patch.setattr(tool_repo, "invalidate_derived", failure)
        with pytest.raises(RuntimeError):
            undo(harness, receipt, message_id=action["id"])
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "knowledge_gap", gap["id"])["status"] == "resolved"
    result = undo(harness, receipt, message_id=action["id"])
    harness.service.memory.retire_fact("alice", before["id"], expected_revision=result["revision"])
    assert tool_repo.get("alice", "knowledge_gap", gap["id"], include_deleted=True)["status"] == "deleted"


def test_answer_and_undo_sources_are_each_bound_to_one_operation(tool_repo: PostgresRepository) -> None:
    harness, _, gap = pending(tool_repo)
    receipt = answer(harness, gap)
    with pytest.raises(EvidenceError):
        answer(harness, gap, operation_id="same-answer-new-operation")
    undo(harness, receipt)
    with pytest.raises(EvidenceError):
        undo(harness, receipt, operation_id="same-undo-new-operation")


def test_answer_is_in_context_dependency_closure_and_change_snapshot_is_forgotten(
    tool_repo: PostgresRepository,
) -> None:
    harness, before, gap = pending(tool_repo)
    source = harness.service.memory.receive("alice", content="合成确认前问题", source_id="before-answer-context")
    frozen = build(harness.service.memory, source)
    receipt = answer(harness, gap)
    assert not tool_repo.verify_versions("alice", frozen.injected_versions)
    fact = tool_repo.get("alice", "fact", before["id"])
    current = harness.service.memory.receive("alice", content="合成面试是哪一天", source_id="after-answer-context")
    result = build(harness.service.memory, current)
    assert result.injected_versions["fact:" + fact["id"]] == fact["revision"]
    answer_ref = fact["source_refs"][1]
    assert result.injected_versions["message:" + answer_ref["message_id"]] == answer_ref["version"]
    harness.service.memory.retire_fact("alice", before["id"], expected_revision=receipt["revision"])
    snapshot = tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)
    assert snapshot["status"] == "deleted" and "before" not in snapshot and "gap_before" not in snapshot


def test_answer_failure_after_fact_write_rolls_back(tool_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    harness, before, gap = pending(tool_repo)
    action = harness.service.memory.receive("alice", content="2026-10-18", source_id="failed-answer", at=NOW)
    service = MemoryEventAnswerService(harness.service.memory, clock=FrozenClock(NOW))
    revision = tool_repo.get_revision("alice")

    def failure(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("合成变更记录写入失败")

    monkeypatch.setattr(service, "_record", failure)
    with pytest.raises(RuntimeError):
        service.confirm(
            "alice", "self", gap["id"], expected_revision=1, message_id=action["id"], operation_id="failed-answer"
        )
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", before["id"]) == before
    assert tool_repo.get("alice", "knowledge_gap", gap["id"])["status"] == "open"


def test_backdated_answer_and_undo_cannot_act_after_later_preparation(tool_repo: PostgresRepository) -> None:
    harness, _, gap = pending(tool_repo)
    earlier = datetime.fromisoformat("2026-10-31T00:00:00+08:00")
    source = harness.service.memory.receive("alice", content="2026-10-18", source_id="backdated-answer", at=earlier)
    with pytest.raises(EvidenceError):
        answer(harness, gap, message_id=source["id"])
    receipt = answer(harness, gap)
    action = harness.service.memory.receive("alice", content=UNDO_DATE_ANSWER, source_id="backdated-undo", at=earlier)
    with pytest.raises(EvidenceError):
        undo(harness, receipt, message_id=action["id"])


def test_reopened_gap_has_new_preparation_clock(tool_repo: PostgresRepository) -> None:
    harness, _, gap = pending(tool_repo)
    receipt = answer(harness, gap)
    later = datetime.fromisoformat("2026-11-02T00:00:00+08:00")
    action = harness.service.memory.receive("alice", content=UNDO_DATE_ANSWER, source_id="later-date-undo", at=later)
    restored = MemoryEventAnswerUndoService(harness.service.memory, clock=FrozenClock(later)).undo(
        "alice",
        "self",
        receipt["ids"][0],
        expected_revision=1,
        message_id=action["id"],
        operation_id="later-date-undo",
    )
    reopened = tool_repo.get("alice", "knowledge_gap", gap["id"])
    assert datetime.fromisoformat(reopened["prepared_at"]) == later
    backdated = harness.service.memory.receive("alice", content="2026-10-19", source_id="backdated-reanswer", at=NOW)
    with pytest.raises(EvidenceError):
        MemoryEventAnswerService(harness.service.memory, clock=FrozenClock(later)).confirm(
            "alice",
            "self",
            gap["id"],
            expected_revision=restored["context_revision"],
            message_id=backdated["id"],
            operation_id="backdated-reanswer",
        )


def test_background_repair_undo_also_refuses_backdated_action(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo)
    receipt = repair(harness, before)
    earlier = datetime.fromisoformat("2026-10-31T00:00:00+08:00")
    action = harness.service.memory.receive(
        "alice", content=UNDO_EVENT_DATE, source_id="backdated-repair-undo", at=earlier
    )
    with pytest.raises(EvidenceError):
        MemoryEventTimeUndoService(harness.service.memory, clock=FrozenClock(NOW)).undo(
            "alice",
            "self",
            receipt["ids"][0],
            record_kind="proposal",
            expected_revision=1,
            message_id=action["id"],
            operation_id="backdated-repair-undo",
        )

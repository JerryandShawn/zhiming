"""Legacy fixtures exercise real PG writes, shared date parsing and explicit source-bound undo."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.memory2_archive import MemoryArchiveService
from mingjing_core.application.memory2_event_dates import MemoryEventTimeRepairService
from mingjing_core.application.memory2_event_dates_undo import UNDO_EVENT_DATE, MemoryEventTimeUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

from .test_context_pg import build
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as base_tool_repo

NOW = datetime.fromisoformat("2026-11-01T00:00:00+08:00")


@pytest.fixture(name="tool_repo")
def event_date_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    previous = get_clock()
    set_clock(FrozenClock(NOW))
    try:
        yield base_tool_repo.__wrapped__(p2_repo, monkeypatch)
    finally:
        set_clock(previous)


def legacy_event(repo: PostgresRepository, text: str = "我下周三参加合成面试", **changes: Any) -> tuple[Any, dict]:
    harness = setup(repo, text)
    result, _, _ = harness.write("background")
    assert result.ok and result.receipt["write_status"] == "saved"
    fact = repo.get("alice", "fact", result.receipt["fact_id"])
    # Explicit historical fixture: old event rows existed before event_at was required.
    fact = repo.update(
        "alice", "fact", fact["id"], {"requested_kind": "event", **changes}, expected_revision=fact["revision"]
    )
    harness.finish()
    return harness, fact


def repair(harness: Any, fact: dict, **changes: Any) -> dict:
    return MemoryEventTimeRepairService(harness.service.memory, clock=FrozenClock(NOW)).repair(
        "alice",
        "self",
        fact["id"],
        **{"expected_revision": fact["revision"], "operation_id": "synthetic-date-repair", **changes},
    )


def undo(harness: Any, receipt: dict, *, gap: bool = False, **changes: Any) -> dict:
    message_id = changes.pop("message_id", None)
    if message_id is None:
        action = harness.service.memory.receive(
            "alice", content=UNDO_EVENT_DATE, source_id="synthetic-date-undo", channel="synthetic", at=NOW
        )
        message_id = action["id"]
    return MemoryEventTimeUndoService(harness.service.memory, clock=FrozenClock(NOW)).undo(
        "alice",
        "self",
        receipt["id"] if gap else receipt["ids"][0],
        **{
            "record_kind": "knowledge_gap" if gap else "proposal",
            "expected_revision": receipt["context_revision"],
            "message_id": message_id,
            "operation_id": "synthetic-date-undo",
            **changes,
        },
    )


def test_original_statement_clock_real_parser_and_replay(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo)
    receipt = repair(harness, before)
    fact = tool_repo.get("alice", "fact", before["id"])
    assert receipt["write_status"] == "updated"
    assert fact["event_at"] == "2026-10-21" and fact["original_expression"] == "下周三"
    assert fact["said_at"] == "2026-10-17T02:30:00+00:00"
    assert fact["content"] == before["content"] and fact["source_refs"] == before["source_refs"]
    revision = tool_repo.get_revision("alice")
    assert repair(harness, before) == receipt
    assert tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert all(before["content"] not in str(row) for row in rows)


@pytest.mark.parametrize("text", ["我这周参加合成面试", "我最近参加合成面试", "我参加合成面试"])
def test_ambiguity_produces_real_deduplicated_gap_without_changing_fact(
    tool_repo: PostgresRepository, text: str
) -> None:
    harness, before = legacy_event(tool_repo, text)
    receipt = repair(harness, before)
    assert receipt["write_status"] == "pending_confirmation" and receipt["kind"] == "knowledge_gap"
    assert tool_repo.get("alice", "fact", before["id"]) == before
    gap = tool_repo.get("alice", "knowledge_gap", receipt["id"])
    assert gap["status"] == "open" and gap["source_refs"] == before["source_refs"]
    assert gap["question"] == "这件事具体是哪一天发生的？"
    assert repair(harness, before, operation_id="another-job") == receipt
    assert len(tool_repo.list("alice", "knowledge_gap")) == 1


def test_exact_undo_invalidates_references_and_replay_is_current(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo, synthetic_extra={"nested": [True, 7]})
    receipt = repair(harness, before)
    tool_repo.put(
        "alice",
        "note",
        "synthetic-date-derived",
        dict(summary="合成日期派生", fact_ids=[before["id"]], source_refs=before["source_refs"]),
        expected_revision=0,
    )
    result = undo(harness, receipt)
    restored = tool_repo.get("alice", "fact", before["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in restored.items() if k not in reserved} == {
        k: v for k, v in before.items() if k not in reserved
    }
    assert result["revision"] > receipt["revision"]
    note = tool_repo.get("alice", "note", "synthetic-date-derived", include_deleted=True)
    assert note["status"] != "active"
    revision = tool_repo.get_revision("alice")
    assert undo(harness, receipt) == result
    assert tool_repo.get_revision("alice") == revision
    with pytest.raises(EvidenceError):
        repair(harness, before)
    tool_repo.update("alice", "fact", before["id"], {"summary": "合成后改"}, expected_revision=result["revision"])
    with pytest.raises(EvidenceError):
        undo(harness, receipt)


def test_gap_dismissal_does_not_touch_fact_or_resurrect_gap(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo, "我这周参加合成面试")
    receipt = repair(harness, before)
    result = undo(harness, receipt, gap=True)
    assert tool_repo.get("alice", "fact", before["id"]) == before
    assert undo(harness, receipt, gap=True) == result
    with pytest.raises(EvidenceError):
        repair(harness, before, operation_id="later-job")
    tombstone = tool_repo.get("alice", "knowledge_gap", receipt["id"], include_deleted=True)
    assert tombstone["status"] == "deleted" and "question" not in tombstone


@pytest.mark.parametrize(
    "changes",
    [
        {"event_at": "2026-10-21"},
        {"owner_timezone": "Bad/Zone"},
        {"owner_timezone": None},
        {"said_at": "2027-01-01T00:00:00+08:00"},
        {"requested_kind": "background"},
    ],
)
def test_invalid_candidates_do_not_mutate(tool_repo: PostgresRepository, changes: dict) -> None:
    harness, before = legacy_event(tool_repo, **changes)
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        repair(harness, before)
    assert tool_repo.get_revision("alice") == revision


def test_owner_revision_and_later_archive_reject_stale_undo(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo)
    with pytest.raises(RevisionConflict):
        repair(harness, before, expected_revision=1)
    service = MemoryEventTimeRepairService(harness.service.memory, clock=FrozenClock(NOW))
    with pytest.raises(ScopeError):
        service.repair("bob", "self", before["id"], expected_revision=before["revision"], operation_id="foreign")
    receipt = repair(harness, before)
    MemoryArchiveService(harness.service.memory, clock=FrozenClock(NOW)).archive(
        "alice",
        "self",
        before["id"],
        expected_revision=receipt["revision"],
        operation_id="after-repair-archive",
    )
    with pytest.raises(EvidenceError):
        undo(harness, receipt)
    assert tool_repo.get("alice", "fact", before["id"])["status"] == "archived"


@pytest.mark.parametrize("withdraw", ["fact", "message", "range"])
def test_withdrawal_prevents_repair_replay_and_undo(tool_repo: PostgresRepository, withdraw: str) -> None:
    harness, before = legacy_event(tool_repo)
    receipt = repair(harness, before)
    if withdraw == "fact":
        harness.service.memory.retire_fact("alice", before["id"], expected_revision=receipt["revision"])
    elif withdraw == "message":
        tool_repo.delete("alice", "message", harness.source["id"], expected_revision=harness.source["revision"])
    else:
        ref = before["source_refs"][0]
        with tool_repo.transaction("alice") as connection:
            tool_repo.revoke(
                connection,
                "alice",
                "source_span",
                "synthetic-date-range",
                "stopped",
                dict(message_id=ref["message_id"], start=ref["start"], end=ref["end"]),
            )
    for call in (lambda: repair(harness, before), lambda: undo(harness, receipt)):
        with pytest.raises((EvidenceError, ScopeError)):
            call()


@pytest.mark.parametrize("mode", ["early", "future", "assistant", "incognito", "thread", "wrong-command"])
def test_undo_action_is_explicit_current_and_source_bound(tool_repo: PostgresRepository, mode: str) -> None:
    harness, before = legacy_event(tool_repo)
    early = harness.service.memory.receive("alice", content=UNDO_EVENT_DATE, source_id="early", at=NOW)
    receipt = repair(harness, before)
    at = datetime.fromisoformat("2027-01-01T00:00:00+08:00") if mode == "future" else NOW
    action = (
        early
        if mode == "early"
        else harness.service.memory.receive(
            "alice",
            content="撤销" if mode == "wrong-command" else UNDO_EVENT_DATE,
            role="assistant" if mode == "assistant" else "user",
            source_id="bad-date-action",
            at=at,
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
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        undo(harness, receipt, message_id=action["id"])
    assert tool_repo.get_revision("alice") == revision


@pytest.mark.parametrize("zone,day", [("America/Los_Angeles", "2026-10-17"), ("Asia/Tokyo", "2026-10-18")])
def test_owner_zone_is_used_instead_of_host_zone(
    tool_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, zone: str, day: str
) -> None:
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    harness, before = legacy_event(tool_repo, "我明天参加合成面试", owner_timezone=zone)
    receipt = repair(harness, before)
    assert tool_repo.get("alice", "fact", receipt["fact_id"])["event_at"] == day


@pytest.mark.parametrize("gap", [True, False])
def test_revoked_record_rejects_cached_repair_and_undo(tool_repo: PostgresRepository, gap: bool) -> None:
    harness, before = legacy_event(tool_repo, "我这周参加合成面试" if gap else "我下周三参加合成面试")
    receipt = repair(harness, before)
    kind, ident = ("knowledge_gap", receipt["id"]) if gap else ("proposal", receipt["ids"][0])
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", kind, ident, "stopped")
    with pytest.raises(EvidenceError):
        repair(harness, before)
    with pytest.raises(EvidenceError):
        undo(harness, receipt, gap=gap)


def test_parser_failure_rolls_back_without_inventing_date(
    tool_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
):
    harness, before = legacy_event(tool_repo)
    service = MemoryEventTimeRepairService(harness.service.memory, clock=FrozenClock(NOW))

    def unavailable(*args: Any, **kwargs: Any) -> None:
        raise EvidenceError("合成解析器不可用")

    monkeypatch.setattr(service.parser, "resolve", unavailable)
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        service.repair("alice", "self", before["id"], expected_revision=before["revision"], operation_id="parser-fail")
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", before["id"]) == before


def test_original_future_clock_and_revoked_consent_are_not_repaired(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo)
    source = tool_repo.update(
        "alice",
        "message",
        harness.source["id"],
        {"at": "2027-01-01T00:00:00+08:00"},
        expected_revision=harness.source["revision"],
    )
    before = tool_repo.update(
        "alice",
        "fact",
        before["id"],
        dict(
            said_at=source["at"], source_refs=[{**ref, "version": source["revision"]} for ref in before["source_refs"]]
        ),
        expected_revision=before["revision"],
    )
    with pytest.raises(EvidenceError):
        repair(harness, before)
    other, candidate = legacy_event(tool_repo)
    proof = tool_repo.put("alice", "consent", "synthetic-date-stopped", {"status": "stopped"}, expected_revision=0)
    candidate = tool_repo.update(
        "alice", "fact", candidate["id"], {"approval_consent_id": proof["id"]}, expected_revision=candidate["revision"]
    )
    with pytest.raises(EvidenceError):
        repair(other, candidate)


def test_gap_enters_real_l3_and_later_fact_revision_hides_it(tool_repo: PostgresRepository) -> None:
    harness, before = legacy_event(tool_repo, "我这周参加合成面试")
    receipt = repair(harness, before)
    source = harness.service.memory.receive("alice", content="合成问题", source_id="date-gap-query")
    result = build(harness.service.memory, source)
    assert receipt["id"] in {row["id"] for row in result.alias_map.values() if row["kind"] == "knowledge_gap"}
    assert result.injected_versions["fact:" + before["id"]] == before["revision"]
    layer = next(layer for layer in result.budget.layers if layer.name == "L3_VOLATILE")
    assert "这件事具体是哪一天发生的？" in str(layer)
    tool_repo.update("alice", "fact", before["id"], {"event_at": "2026-10-19"}, expected_revision=before["revision"])
    later = build(harness.service.memory, source)
    assert receipt["id"] not in {row["id"] for row in later.alias_map.values()}


def test_one_action_cannot_authorize_multiple_jobs_and_failed_cascade_rolls_back(
    tool_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness, before = legacy_event(tool_repo)
    receipt = repair(harness, before)
    action = harness.service.memory.receive("alice", content=UNDO_EVENT_DATE, source_id="cascade-date-undo", at=NOW)
    revision = tool_repo.get_revision("alice")

    def failed(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("合成派生清理失败")

    with monkeypatch.context() as patch:
        patch.setattr(tool_repo, "invalidate_derived", failed)
        with pytest.raises(RuntimeError):
            undo(harness, receipt, message_id=action["id"])
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", before["id"])["event_at"] == "2026-10-21"
    assert tool_repo.get("alice", "proposal", receipt["ids"][0])["status"] == "applied"
    undo(harness, receipt, message_id=action["id"])
    with pytest.raises(EvidenceError):
        undo(harness, receipt, message_id=action["id"], operation_id="other-date-job")
    service = MemoryEventTimeUndoService(
        harness.service.memory, clock=FrozenClock(datetime.fromisoformat("2026-10-31T00:00:00+08:00"))
    )
    with pytest.raises(EvidenceError):
        service.undo(
            "alice",
            "self",
            receipt["ids"][0],
            record_kind="proposal",
            expected_revision=1,
            message_id=action["id"],
            operation_id="synthetic-date-undo",
        )

"""Real PG archival is scoped, idempotent and removable through existing privacy cascades."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.memory2_archive import MemoryArchiveService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock

from .test_toolkit_pg import Parser, setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def archive_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def event(repo: PostgresRepository, **metadata: Any) -> tuple[Any, dict, FrozenClock]:
    harness = setup(repo, "我下周三参加合成面试", parser=Parser())
    result, _, _ = harness.write("event")
    assert result.ok
    fact = repo.get("alice", "fact", result.receipt["fact_id"])
    if metadata:
        fact = repo.update("alice", "fact", fact["id"], metadata, expected_revision=fact["revision"])
    harness.finish()
    return (
        harness,
        fact,
        FrozenClock(datetime.fromisoformat("2026-10-22T00:00:00+08:00")),
    )


def archive(harness: Any, fact: dict, clock: FrozenClock, **changes: Any) -> dict:
    return MemoryArchiveService(harness.service.memory, clock=clock).archive(
        "alice",
        "self",
        fact["id"],
        **{
            "expected_revision": fact["revision"],
            "operation_id": "synthetic-archive",
            **changes,
        },
    )


def test_archive_preserves_history_filters_current_projections_and_is_replay_safe(
    tool_repo: PostgresRepository,
) -> None:
    harness, fact, clock = event(tool_repo)
    tool_repo.put(
        "alice",
        "note",
        "synthetic-projection",
        {"summary": "合成面试", "fact_ids": [fact["id"]], "source_refs": fact["source_refs"]},
        expected_revision=0,
    )
    receipt = archive(harness, fact, clock)
    current = tool_repo.get("alice", "fact", fact["id"])
    assert current["status"] == "archived" and current["content"] == fact["content"]
    assert current["source_refs"] == fact["source_refs"]
    assert current["archive_deadline"] == "2026-10-21T16:00:00+00:00"
    assert harness.service.memory.facts("alice") == []
    assert fact["id"] in {row["id"] for row in harness.service.memory.facts("alice", include_inactive=True)}
    assert tool_repo.get("alice", "note", "synthetic-projection")["status"] == "active"
    reader = setup(tool_repo, "查询合成面试")
    found, _ = reader.call("memory_search", {"query": "合成面试", "kinds": ["fact", "note"]})
    assert found.ok and found.data["items"] == []
    reader.finish()
    change = tool_repo.get("alice", "proposal", receipt["ids"][0])
    assert change["before"]["content"] == fact["content"]
    revision = tool_repo.get_revision("alice")
    clock.advance(timedelta(days=1))
    assert archive(harness, fact, clock) == receipt
    assert tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        receipts = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert all("合成面试" not in str(row) for row in receipts)


def test_date_event_is_not_archived_early_or_based_on_host_timezone(
    tool_repo: PostgresRepository,
) -> None:
    harness, fact, clock = event(tool_repo)
    clock.at = datetime.fromisoformat("2026-10-21T15:59:59+00:00")
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)
    assert tool_repo.get_revision("alice") == revision
    clock.advance(timedelta(seconds=1))
    assert archive(harness, fact, clock)["write_status"] == "archived"


@pytest.mark.parametrize("metadata", [{"event_end": "未知"}, {"said_at": "2026-12-01T00:00:00+08:00"}])
def test_invalid_or_future_source_dates_do_not_archive(tool_repo: PostgresRepository, metadata: dict) -> None:
    harness, fact, clock = event(tool_repo, **metadata)
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)
    assert tool_repo.get_revision("alice") == revision


def test_revision_and_owner_subject_guards(tool_repo: PostgresRepository) -> None:
    harness, fact, clock = event(tool_repo)
    service = MemoryArchiveService(harness.service.memory, clock=clock)
    with pytest.raises(RevisionConflict):
        service.archive("alice", "self", fact["id"], expected_revision=1, operation_id="stale")
    with pytest.raises(ScopeError):
        service.archive(
            "bob",
            "self",
            fact["id"],
            expected_revision=fact["revision"],
            operation_id="cross-owner",
        )
    tool_repo.create_subject("alice", "synthetic-other", "合成人物")
    with pytest.raises(ScopeError):
        service.archive(
            "alice",
            "synthetic-other",
            fact["id"],
            expected_revision=fact["revision"],
            operation_id="cross-subject",
        )


def test_source_change_rejects_atomic_archive(tool_repo: PostgresRepository) -> None:
    harness, fact, clock = event(tool_repo)
    source = tool_repo.get("alice", "message", harness.source["id"])
    tool_repo.update(
        "alice",
        "message",
        source["id"],
        {"synthetic_revision": True},
        expected_revision=source["revision"],
    )
    revision = tool_repo.get_revision("alice")
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)
    assert tool_repo.get_revision("alice") == revision
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"


def test_forget_archived_fact_clears_snapshot_and_disallows_cached_replay(
    tool_repo: PostgresRepository,
) -> None:
    harness, fact, clock = event(tool_repo)
    receipt = archive(harness, fact, clock)
    archived = tool_repo.get("alice", "fact", fact["id"])
    harness.service.memory.retire_fact("alice", fact["id"], expected_revision=archived["revision"])
    change = tool_repo.get("alice", "proposal", receipt["ids"][0], include_deleted=True)
    assert change["status"] == "deleted" and "before" not in change
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)


def test_clock_injection_does_not_change_global_clock(
    tool_repo: PostgresRepository,
) -> None:
    harness, fact, clock = event(tool_repo)
    original = get_clock()
    try:
        set_clock(FrozenClock(datetime.fromisoformat("2026-01-01T00:00:00+08:00")))
        assert archive(harness, fact, clock)["write_status"] == "archived"
    finally:
        set_clock(original)


@pytest.mark.parametrize("changes", [{"incognito": True}, {"policy": {"origin": "migration", "run_context": False}}])
def test_nonpersistent_or_nonuser_authority_is_not_archived(tool_repo: PostgresRepository, changes: dict) -> None:
    harness, fact, clock = event(tool_repo)
    source = tool_repo.get("alice", "message", harness.source["id"])
    source = tool_repo.update("alice", "message", source["id"], changes, expected_revision=source["revision"])
    refs = [{**ref, "version": source["revision"]} for ref in fact["source_refs"]]
    fact = tool_repo.update("alice", "fact", fact["id"], {"source_refs": refs}, expected_revision=fact["revision"])
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"


def test_revoked_confirmation_cannot_authorize_archival(tool_repo: PostgresRepository) -> None:
    harness, fact, clock = event(tool_repo)
    proof = tool_repo.put("alice", "consent", "synthetic-archive-proof", {"status": "stopped"}, expected_revision=0)
    fact = tool_repo.update(
        "alice", "fact", fact["id"], {"approval_consent_id": proof["id"]}, expected_revision=fact["revision"]
    )
    with pytest.raises(EvidenceError):
        archive(harness, fact, clock)
    assert tool_repo.get("alice", "fact", fact["id"])["status"] == "active"

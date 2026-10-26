"""Real v4 writes merge equivalent facts and owner undo restores the exact payload."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_undo import MemoryMergeUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import Harness, setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def merge_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def merged(repo: PostgresRepository) -> tuple[dict[str, Any], Harness, Any, Any, dict[str, Any]]:
    first = setup(repo, "我喜欢合成徒步")
    saved, _, _ = first.write("preference")
    before = repo.get("alice", "fact", saved.receipt["fact_id"])
    first.finish()
    second = setup(repo, "我喜欢合成徒步")
    result, ctx, args = second.write("preference")
    assert result.ok and result.receipt.get("code") == "memory2_merged"
    assert result.receipt["fact_id"] == before["id"]
    return before, second, result, ctx, args


def undo(repo: PostgresRepository, result: Any, *, key: str = "synthetic-undo") -> dict[str, Any]:
    message = MemoryService(repo).receive("alice", content="撤销这次记忆合并", source_id=key, channel="synthetic")
    return MemoryMergeUndoService(MemoryService(repo)).undo(
        "alice",
        "self",
        result.receipt["ids"][0],
        expected_revision=1,
        message_id=message["id"],
        operation_id=key,
    )


def payload(row: dict[str, Any]) -> dict[str, Any]:
    reserved = {"revision", "created_at", "updated_at"}
    return {key: value for key, value in row.items() if key not in reserved}


def test_merge_compares_instants_across_utc_and_owner_offsets(tool_repo, monkeypatch):
    first = setup(tool_repo, "我喜欢合成晨读")
    old, _, _ = first.write("preference")
    first.finish()
    monkeypatch.setattr(f"{setup.__module__}.SAID_AT", datetime.fromisoformat("2026-10-17T02:31:00+00:00"))
    second = setup(tool_repo, "我喜欢合成晨读")
    merged, _, _ = second.write("preference")
    assert merged.ok and merged.receipt["code"] == "memory2_merged"
    assert merged.receipt["fact_id"] == old.receipt["fact_id"]
    assert len(second.service.memory.facts("alice")) == 1
    second.finish()


def test_equivalent_assertions_are_one_active_fact_with_both_sources(tool_repo: PostgresRepository) -> None:
    before, h, result, ctx, args = merged(tool_repo)
    facts = h.service.memory.facts("alice")
    assert len(facts) == 1 and facts[0]["id"] == before["id"]
    assert len(facts[0]["source_refs"]) == 2
    revision = tool_repo.get_revision("alice")
    assert h.registry.execute("memory_write", args, ctx).receipt == result.receipt
    assert tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        receipts = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert all("合成徒步" not in str(row) for row in receipts)


def test_undo_restores_fields_and_propagates_to_derived_content(tool_repo: PostgresRepository) -> None:
    before, h, result, ctx, args = merged(tool_repo)
    tool_repo.put(
        "alice", "note", "synthetic-derived", {"summary": "合成推断", "fact_ids": [before["id"]]}, expected_revision=0
    )
    receipt = undo(tool_repo, result)
    restored = tool_repo.get("alice", "fact", before["id"])
    assert payload(restored) == payload(before)
    assert receipt["fact_id"] == before["id"] and receipt["revision"] > before["revision"]
    assert tool_repo.get("alice", "note", "synthetic-derived", include_deleted=True)["status"] == "deleted"
    assert not h.registry.execute("memory_write", args, ctx).ok
    revision = tool_repo.get_revision("alice")
    assert undo(tool_repo, result) == receipt
    assert tool_repo.get_revision("alice") == revision


def test_changed_target_blocks_undo_atomically(tool_repo: PostgresRepository) -> None:
    before, _, result, _, _ = merged(tool_repo)
    current = tool_repo.get("alice", "fact", before["id"])
    tool_repo.update("alice", "fact", before["id"], {"summary": "合成用户修改"}, expected_revision=current["revision"])
    with pytest.raises(RevisionConflict):
        undo(tool_repo, result)
    assert len(tool_repo.get("alice", "fact", before["id"])["source_refs"]) == 2


def test_forgetting_original_purges_undo_snapshot_and_prevents_revival(tool_repo: PostgresRepository) -> None:
    before, _, result, _, _ = merged(tool_repo)
    current = tool_repo.get("alice", "fact", before["id"])
    MemoryService(tool_repo).retire_fact("alice", before["id"], expected_revision=current["revision"])
    change = tool_repo.get("alice", "proposal", result.receipt["ids"][0], include_deleted=True)
    assert change["status"] == "deleted" and "before" not in change
    with pytest.raises((EvidenceError, ScopeError)):
        undo(tool_repo, result)
    assert MemoryService(tool_repo).facts("alice") == []


def test_inactive_or_stale_fact_is_never_merge_target(tool_repo: PostgresRepository) -> None:
    first = setup(tool_repo, "我喜欢合成徒步")
    result, _, _ = first.write("preference")
    first.finish()
    tool_repo.update("alice", "message", first.source["id"], {"synthetic_revision": True}, expected_revision=1)
    second = setup(tool_repo, "我喜欢合成徒步")
    new, _, _ = second.write("preference")
    assert new.ok and new.receipt["fact_id"] != result.receipt["fact_id"]
    assert "ids" not in new.receipt


def test_opposite_assertion_is_proposed_without_fuzzy_merge(tool_repo: PostgresRepository) -> None:
    first = setup(tool_repo, "我喜欢合成徒步")
    first.write("preference")
    first.finish()
    second = setup(tool_repo, "我不喜欢合成徒步")
    result, _, _ = second.write("preference")
    assert not result.ok and result.receipt["code"] == "memory2_possible_conflict"
    assert len(second.service.memory.facts("alice")) == 1
    assert second.service.memory.facts("alice")[0]["content"] == "我喜欢合成徒步"

"""Archive undo restores exact business fields and rejects stale or withdrawn authority."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_archive_undo import MemoryArchiveUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_memory2_archive_pg import archive, event
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def archive_undo_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def undo(repo: PostgresRepository, receipt: dict, **changes: Any) -> dict:
    memory = MemoryService(repo)
    action = memory.receive(
        "alice", content="撤销这次记忆归档", source_id="synthetic-undo-archive", channel="synthetic"
    )
    return MemoryArchiveUndoService(memory).undo(
        "alice",
        "self",
        receipt["ids"][0],
        **{"expected_revision": 1, "message_id": action["id"], "operation_id": "synthetic-archive-undo", **changes},
    )


def test_exact_restore_idempotency_and_no_replay_of_old_archive(tool_repo: PostgresRepository) -> None:
    harness, before, clock = event(tool_repo, synthetic_extra={"nested": [True, 7]})
    receipt = archive(harness, before, clock)
    restored_receipt = undo(tool_repo, receipt)
    restored = tool_repo.get("alice", "fact", before["id"])
    reserved = {"revision", "created_at", "updated_at"}
    assert {k: v for k, v in restored.items() if k not in reserved} == {
        k: v for k, v in before.items() if k not in reserved
    }
    assert restored_receipt["revision"] > receipt["revision"]
    revision = tool_repo.get_revision("alice")
    assert undo(tool_repo, receipt) == restored_receipt
    assert tool_repo.get_revision("alice") == revision
    with pytest.raises(EvidenceError):
        archive(harness, before, clock)
    assert tool_repo.get("alice", "fact", before["id"])["status"] == "active"


def test_undo_refuses_changed_fact_without_losing_edits(tool_repo: PostgresRepository) -> None:
    harness, before, clock = event(tool_repo)
    receipt = archive(harness, before, clock)
    tool_repo.update("alice", "fact", before["id"], {"summary": "合成用户修改"}, expected_revision=receipt["revision"])
    with pytest.raises(RevisionConflict):
        undo(tool_repo, receipt)
    assert tool_repo.get("alice", "fact", before["id"])["summary"] == "合成用户修改"


@pytest.mark.parametrize("withdraw", ["fact", "message", "range"])
def test_undo_never_restores_withdrawn_originals(tool_repo: PostgresRepository, withdraw: str) -> None:
    harness, before, clock = event(tool_repo)
    receipt = archive(harness, before, clock)
    if withdraw == "fact":
        harness.service.memory.retire_fact("alice", before["id"], expected_revision=receipt["revision"])
    elif withdraw == "message":
        tool_repo.delete("alice", "message", harness.source["id"], expected_revision=harness.source["revision"])
    else:
        with tool_repo.transaction("alice") as connection:
            ref = before["source_refs"][0]
            tool_repo.revoke(
                connection,
                "alice",
                "source_span",
                "synthetic-range",
                "stopped",
                {
                    "message_id": ref["message_id"],
                    "start": ref["start"],
                    "end": ref["end"],
                },
            )
    with pytest.raises((EvidenceError, ScopeError)):
        undo(tool_repo, receipt)
    assert tool_repo.get("alice", "fact", before["id"], include_deleted=True)["status"] != "active"


@pytest.mark.parametrize(
    "text,role,incognito",
    [("请撤销", "user", False), ("撤销这次记忆归档", "assistant", False), ("撤销这次记忆归档", "user", True)],
)
def test_explicit_user_action_required(tool_repo: PostgresRepository, text: str, role: str, incognito: bool) -> None:
    harness, before, clock = event(tool_repo)
    receipt = archive(harness, before, clock)
    action = harness.service.memory.receive(
        "alice", content=text, role=role, source_id="synthetic-invalid-undo", channel="synthetic"
    )
    if incognito:
        action = tool_repo.update(
            "alice", "message", action["id"], {"incognito": True}, expected_revision=action["revision"]
        )
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt, message_id=action["id"])
    assert tool_repo.get("alice", "fact", before["id"])["status"] == "archived"


def test_undo_cached_receipt_rechecks_restored_fact(tool_repo: PostgresRepository) -> None:
    harness, before, clock = event(tool_repo)
    receipt = archive(harness, before, clock)
    restored = undo(tool_repo, receipt)
    harness.service.memory.retire_fact("alice", before["id"], expected_revision=restored["revision"])
    with pytest.raises(EvidenceError):
        undo(tool_repo, receipt)

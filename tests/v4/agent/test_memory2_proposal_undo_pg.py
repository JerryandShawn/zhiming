"""Undo category confirmation restores memory fields and retires dependent grants."""

from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_proposal_undo import MemoryProposalUndoService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.repositories.postgres import PostgresRepository

from .test_memory2_proposals_pg import confirm, pending
from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def undo_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def undo(repo: PostgresRepository, ident: str, *, revision: int = 2) -> dict[str, Any]:
    memory = MemoryService(repo)
    action = memory.receive(
        "alice",
        content="撤销这次记忆确认",
        source_id="undo-confirmation",
        channel="synthetic",
        at=SAID_AT + timedelta(minutes=2),
    )
    return MemoryProposalUndoService(memory).undo(
        "alice",
        "self",
        ident,
        expected_revision=revision,
        message_id=action["id"],
        operation_id="synthetic-undo-confirmation",
    )


def business(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in {"revision", "created_at", "updated_at"}}


def test_undo_restores_pending_proposal_and_exact_memory_settings(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    original = tool_repo.get("alice", "proposal", ident)
    settings = tool_repo.assert_scope("alice")["settings"]
    receipt = confirm(tool_repo, ident, remember=True)
    undone = undo(tool_repo, ident)
    assert business(tool_repo.get("alice", "proposal", ident)) == business(original)
    assert tool_repo.assert_scope("alice")["settings"] == settings
    assert MemoryService(tool_repo).facts("alice") == []
    assert tool_repo.get("alice", "fact", receipt["fact_id"])["status"] == "retired"
    revision = tool_repo.get_revision("alice")
    assert undo(tool_repo, ident) == undone and tool_repo.get_revision("alice") == revision


def test_undo_retires_later_auto_saved_facts_and_invalidates_their_notes(tool_repo: PostgresRepository) -> None:
    first, ident = pending(tool_repo)
    confirm(tool_repo, ident, remember=True)
    first.finish()
    later = setup(tool_repo, "我这周复诊了")
    saved, _, _ = later.write("background")
    assert saved.ok
    tool_repo.put(
        "alice",
        "note",
        "derived-health",
        {"summary": "合成整理", "fact_ids": [saved.receipt["fact_id"]]},
        expected_revision=0,
    )
    result = undo(tool_repo, ident)
    assert saved.receipt["fact_id"] in result["affected_ids"]
    assert MemoryService(tool_repo).facts("alice") == []
    assert tool_repo.get("alice", "note", "derived-health", include_deleted=True)["status"] == "deleted"


def test_undo_then_new_confirmation_uses_new_evidence_not_retired_identity(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    first = confirm(tool_repo, ident)
    undo(tool_repo, ident)
    revision = tool_repo.get("alice", "proposal", ident)["revision"]
    second = confirm(tool_repo, ident, operation="new-confirmation", revision=revision)
    assert first["fact_id"] != second["fact_id"]
    assert tool_repo.get("alice", "fact", first["fact_id"])["status"] == "retired"
    assert len(MemoryService(tool_repo).facts("alice")) == 1


def test_unrelated_owner_settings_survive_memory_undo(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    confirm(tool_repo, ident, remember=True)
    settings = dict(tool_repo.assert_scope("alice")["settings"], synthetic_unrelated=True)
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(tool_repo.table("core_owners")),
            (Jsonb(settings), "alice"),
        )
    undo(tool_repo, ident)
    assert tool_repo.assert_scope("alice")["settings"] == {
        "auto_save_low_sensitivity": True,
        "synthetic_unrelated": True,
    }


def test_changed_memory_grants_block_undo_without_partial_retirement(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    saved = confirm(tool_repo, ident, remember=True)
    settings = dict(tool_repo.assert_scope("alice")["settings"], auto_save_categories=["health", "money"])
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(tool_repo.table("core_owners")),
            (Jsonb(settings), "alice"),
        )
    with pytest.raises(RevisionConflict):
        undo(tool_repo, ident)
    assert tool_repo.get("alice", "fact", saved["fact_id"])["status"] == "active"
    assert tool_repo.get("alice", "proposal", ident)["status"] == "accepted"


def test_withdrawn_original_cannot_be_revived_by_undo_or_replay(tool_repo: PostgresRepository) -> None:
    _, ident = pending(tool_repo)
    saved = confirm(tool_repo, ident, remember=True)
    memory = MemoryService(tool_repo)
    current = tool_repo.get("alice", "fact", saved["fact_id"])
    memory.retire_fact("alice", current["id"], expected_revision=current["revision"])
    with pytest.raises(EvidenceError):
        confirm(tool_repo, ident, remember=True)
    with pytest.raises(EvidenceError):
        undo(tool_repo, ident)
    assert memory.facts("alice") == []

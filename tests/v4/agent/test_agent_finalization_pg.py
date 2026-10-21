"""A real PG transaction publishes a v4 answer and its lineage, or nothing."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.envelope import validated_result
from mingjing_core.application.agent_commit_versions import RegenerationRequired
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_tool_repo


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_tool_repo.__wrapped__(p2_repo, monkeypatch)


def prepare(repo: PostgresRepository) -> tuple[Any, dict[str, int], int]:
    h = setup(repo, "我喜欢安静的合成书房")
    versions = {"message:" + h.source["id"]: h.source["revision"]}
    repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    return h, versions, repo.get_revision("alice")


def finish(h: Any, versions: dict[str, int], revision: int, **changes: Any) -> dict[str, Any]:
    return AgentFinalizer(h.repo, clock=h.service.clock).finalize(
        h.run,
        text=changes.pop("text", "合成回答"),
        alias_map=changes.pop("alias_map", {}),
        versions=versions,
        snapshot_revision=revision,
        **changes,
    )


def test_atomic_v4_commit_keeps_legacy_commit_contract(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    with pytest.raises(EvidenceError):
        tool_repo.commit_run(
            "alice",
            h.run["id"],
            versions,
            {"schema_version": "core4.0", "validation": {"status": "validated"}},
            h.run["lease_token"],
        )
    result = finish(h, versions, revision)
    stored = tool_repo.fetch_run("alice", h.run["id"])
    assert validated_result(result) and stored["status"] == "succeeded" and stored["result"] == result
    reply = tool_repo.get("alice", "message", result["message_id"])
    assert reply["role"] == "assistant" and reply["source_ids"] == [h.source["id"]]
    assert len([row for row in tool_repo.list("alice", "message") if row.get("role") == "assistant"]) == 1
    with pytest.raises(LeaseConflict):
        finish(h, versions, revision)
    assert tool_repo.get("alice", "message", result["message_id"])["revision"] == 1


@pytest.mark.parametrize("change", ["cancel", "epoch", "runtime", "lease", "incognito"])
def test_invalid_current_authority_cannot_publish(tool_repo: PostgresRepository, change: str) -> None:
    h, versions, revision = prepare(tool_repo)
    updates = {
        "cancel": "cancel_requested_at=now()",
        "epoch": "retry_epoch=1",
        "runtime": "runtime='v3'",
        "lease": "lease_until=now()-interval '1 second'",
        "incognito": "thread_id='incognito:synthetic'",
    }
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET " + updates[change] + " WHERE id=%s").format(tool_repo.table("core_runs")),
            (h.run["id"],),
        )
    with pytest.raises((EvidenceError, LeaseConflict)):
        finish(h, versions, revision)
    assert not [row for row in tool_repo.list("alice", "message") if row.get("role") == "assistant"]


def test_unknown_alias_removed_and_foreign_alias_cannot_publish(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    with pytest.raises(EvidenceError):
        finish(h, versions, revision, text="〔f1〕", alias_map={"f1": {"kind": "fact", "id": "outside", "revision": 1}})
    assert tool_repo.fetch_run("alice", h.run["id"])["status"] == "running"
    result = finish(
        h,
        versions,
        revision,
        text="依据〔m1〕，未知〔f404〕",
        alias_map={"m1": {"kind": "message", "id": h.source["id"], "revision": 1}},
    )
    assert "f404" not in result["text"] and result["meta"]["structural_warnings"][0]["count"] == 1


def test_invented_question_is_not_a_real_ask_user_step(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    with pytest.raises(EvidenceError):
        finish(
            h,
            versions,
            revision,
            asked={"question": "合成问题？", "options": [], "why": "合成", "allow_free_text": True},
        )
    assert tool_repo.fetch_run("alice", h.run["id"])["result"] is None


def test_current_source_change_or_missing_dependency_is_not_silently_published(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    tool_repo.update("alice", "message", h.source["id"], {"content": "改过的合成原话"}, expected_revision=1)
    with pytest.raises((EvidenceError, RevisionConflict, ScopeError)):
        finish(h, versions, revision)
    assert tool_repo.fetch_run("alice", h.run["id"])["result"] is None


def test_fake_owner_and_request_are_not_authority(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    fake = replace(h, run=dict(h.run, owner_user_id="bob"))
    with pytest.raises(ScopeError):
        finish(fake, versions, revision)
    assert tool_repo.fetch_run("alice", h.run["id"])["result"] is None


def test_used_source_withdrawal_requests_one_regeneration_without_restoring_body(tool_repo: PostgresRepository) -> None:
    h, versions, revision = prepare(tool_repo)
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "message", h.source["id"], "deleted")
    with pytest.raises(RegenerationRequired):
        finish(h, versions, revision)
    assert tool_repo.fetch_run("alice", h.run["id"])["result"] is None
    with tool_repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET retry_epoch=1 WHERE id=%s").format(tool_repo.table("core_runs")), (h.run["id"],)
        )
    h.run["retry_epoch"] = 1
    with pytest.raises(EvidenceError, match="再次撤销"):
        finish(h, versions, revision)


def test_unrelated_revocation_and_write_do_not_invalidate_exact_injected_entities(
    tool_repo: PostgresRepository,
) -> None:
    h, versions, revision = prepare(tool_repo)
    with tool_repo.transaction("alice") as connection:
        tool_repo.revoke(connection, "alice", "fact", "unrelated-synthetic", "deleted")
    tool_repo.put("alice", "note", "unrelated-note", {"summary": "无关合成笔记"})
    result = finish(h, versions, revision)
    assert validated_result(result) and tool_repo.fetch_run("alice", h.run["id"])["status"] == "succeeded"

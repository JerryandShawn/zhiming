"""The real writer proposes opposing facts without overwriting or inventing consent."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.dependencies import entity_dependency

from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as base_tool_repo


@pytest.fixture(name="tool_repo")
def conflicts_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    return base_tool_repo.__wrapped__(p2_repo, monkeypatch)


def conflict(repo: Any) -> tuple[Any, dict, Any, Any, dict]:
    previous = setup(repo, "我喜欢合成徒步")
    saved, _, _ = previous.write("preference")
    old = repo.get("alice", "fact", saved.receipt["fact_id"])
    previous.finish()
    current = setup(repo, "我不喜欢合成徒步")
    result, ctx, args = current.write("preference")
    assert result.receipt["code"] == "memory2_possible_conflict"
    return current, old, result, ctx, args


def test_real_tool_returns_one_p3_proposal_and_preserves_old_fact(tool_repo: Any) -> None:
    current, old, result, ctx, args = conflict(tool_repo)
    assert not result.ok and result.receipt["write_status"] == "pending_confirmation"
    assert (
        result.data["possible_conflict"]["summary"]
        == "以前你说“我喜欢合成徒步”，现在说“我不喜欢合成徒步”，以哪个为准？"
    )
    assert result.data["possible_conflict"]["vector_available"] is False
    proposal = tool_repo.get("alice", "proposal", result.receipt["id"])
    assert proposal["proposal_type"] == "memory_conflict" and proposal["fact_ids"] == [old["id"]]
    assert len(proposal["source_refs"]) == 2
    assert [row["id"] for row in current.service.memory.facts("alice")] == [old["id"]]
    assert tool_repo.get("alice", "fact", old["id"])["revision"] == old["revision"]
    revision = tool_repo.get_revision("alice")
    assert current.registry.execute("memory_write", args, ctx) == result
    assert tool_repo.get_revision("alice") == revision
    with tool_repo.transaction("alice") as connection:
        receipts = connection.execute(
            sql.SQL("SELECT receipt FROM {}").format(tool_repo.table("core_mutation_requests"))
        ).fetchall()
    assert all("合成徒步" not in str(row) for row in receipts)


def test_shared_proposal_rejection_drops_new_assertion_without_changing_old(tool_repo: Any) -> None:
    current, old, result, ctx, args = conflict(tool_repo)
    action = current.service.memory.receive(
        "alice", content="不要保存这条记忆", source_id="synthetic-conflict-reject", channel="synthetic"
    )
    receipt = MemoryProposalService(current.service.memory).reject(
        "alice",
        "self",
        result.receipt["id"],
        expected_revision=result.receipt["revision"],
        message_id=action["id"],
        operation_id="synthetic-conflict-reject",
    )
    assert receipt["write_status"] == "stopped"
    assert tool_repo.get("alice", "proposal", result.receipt["id"], include_deleted=True)["status"] == "deleted"
    assert tool_repo.get("alice", "fact", old["id"])["revision"] == old["revision"]
    assert not current.registry.execute("memory_write", args, ctx).ok


def test_generic_save_click_cannot_select_new_conflicting_truth(tool_repo: Any) -> None:
    current, old, result, _, _ = conflict(tool_repo)
    action = current.service.memory.receive(
        "alice", content="请保存这条记忆", source_id="synthetic-ambiguous-conflict-accept", channel="synthetic"
    )
    with pytest.raises(EvidenceError, match="选择"):
        MemoryProposalService(current.service.memory).accept(
            "alice",
            "self",
            result.receipt["id"],
            expected_revision=result.receipt["revision"],
            message_id=action["id"],
            remember_category=False,
            operation_id="synthetic-ambiguous-conflict-accept",
        )
    assert [row["id"] for row in tool_repo.list("alice", "fact")] == [old["id"]]
    assert tool_repo.list("alice", "consent") == []


@pytest.mark.parametrize("target", ["old", "incoming"])
def test_withdrawing_either_original_purges_pending_proposal(tool_repo: Any, target: str) -> None:
    current, old, result, ctx, args = conflict(tool_repo)
    if target == "old":
        current.service.memory.retire_fact("alice", old["id"], expected_revision=old["revision"])
    else:
        source = current.source
        tool_repo.delete("alice", "message", source["id"], expected_revision=source["revision"])
        tool_repo.invalidate_derived("alice", [], [source["id"]])
    proposal = tool_repo.get("alice", "proposal", result.receipt["id"], include_deleted=True)
    assert proposal["status"] == "deleted" and "source_refs" not in proposal
    assert not current.registry.execute("memory_write", args, ctx).ok


def test_stale_old_fact_cannot_be_replayed_as_a_current_conflict(tool_repo: Any) -> None:
    current, old, _, ctx, args = conflict(tool_repo)
    tool_repo.update("alice", "fact", old["id"], {"synthetic_revision": True}, expected_revision=old["revision"])
    result = current.registry.execute("memory_write", args, ctx)
    assert not result.ok and result.receipt is None


def test_stale_old_source_does_not_create_false_conflict(tool_repo: Any) -> None:
    previous = setup(tool_repo, "我喜欢合成徒步")
    previous.write("preference")
    previous.finish()
    source = previous.source
    tool_repo.update(
        "alice", "message", source["id"], {"synthetic_revision": True}, expected_revision=source["revision"]
    )
    current = setup(tool_repo, "我不喜欢合成徒步")
    result, _, _ = current.write("preference")
    assert result.ok and result.receipt["write_status"] == "saved"
    assert tool_repo.list("alice", "proposal") == []


def test_future_old_assertion_is_not_read_into_an_earlier_run(tool_repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from . import test_toolkit_pg

    at = test_toolkit_pg.SAID_AT
    monkeypatch.setattr(test_toolkit_pg, "SAID_AT", at + timedelta(days=1))
    previous = setup(tool_repo, "我喜欢合成徒步")
    previous.write("preference")
    previous.finish()
    monkeypatch.setattr(test_toolkit_pg, "SAID_AT", at)
    current = setup(tool_repo, "我不喜欢合成徒步")
    result, _, _ = current.write("preference")
    assert result.ok and tool_repo.list("alice", "proposal") == []


def test_other_topic_is_saved_without_silent_merging(tool_repo: Any) -> None:
    previous = setup(tool_repo, "我喜欢合成徒步")
    previous.write("preference")
    previous.finish()
    current = setup(tool_repo, "我不喜欢合成夜班")
    result, _, _ = current.write("preference")
    assert result.ok and len(tool_repo.list("alice", "fact")) == 2
    assert tool_repo.list("alice", "proposal") == []


def test_optout_stops_before_conflict_proposal_creation(tool_repo: Any) -> None:
    previous = setup(tool_repo, "我喜欢合成徒步")
    previous.write("preference")
    previous.finish()
    current = setup(tool_repo, "我不喜欢合成徒步，这条不要保存")
    result, _, _ = current.write("preference", quote="我不喜欢合成徒步")
    assert result.receipt["write_status"] == "stopped"
    assert tool_repo.list("alice", "proposal") == []


def test_existing_loop_lineage_attests_old_fact_and_both_originals(tool_repo: Any) -> None:
    current, old, result, _, _ = conflict(tool_repo)
    versions, records = verified_versions(
        current.service, tool_repo.fetch_run("alice", current.run["id"]), "memory_write", result
    )
    assert entity_dependency("proposal", result.receipt["id"]) in versions
    assert versions[entity_dependency("fact", old["id"])] == old["revision"]
    for ref in [*old["source_refs"], {"message_id": current.source["id"], "version": current.source["revision"]}]:
        assert versions[entity_dependency("message", ref["message_id"])] == ref["version"]
    assert {row["kind"] for row in records} == {"proposal", "fact", "message"}

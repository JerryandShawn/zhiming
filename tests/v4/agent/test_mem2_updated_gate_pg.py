"""v58 H1: native updated writes carry exact new and historical dependencies."""

from copy import deepcopy

import pytest

from mingjing_core.agent.envelope import public_receipt
from mingjing_core.agent.event_contracts import MemoryReceipt
from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.application.agent_commit_versions import _own_revision, persisted_receipts, reconcile_versions
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.agent_updated_receipts import public_updated_receipts
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, RevisionConflict
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository

from .test_toolkit_pg import SAID_AT, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def updated(repo: PostgresRepository, *, receipt_revision: object = None, change_revision_delta: int = 0):
    memory = MemoryService(repo)
    source = memory.receive("alice", content="我喜欢喝茶", source_id="old-pref", at=SAID_AT)
    old = memory.save_fact("alice", "self", source["id"], "我喜欢喝茶", "preference")
    h = setup(repo, "我现在改喝咖啡，不再喝茶")
    new = memory.save_fact("alice", "self", h.source["id"], h.source["content"], "preference")
    step = h.journal.next_or_replay(h.run, kind="tool", name="memory_write", input_fp="a" * 64)
    operation = step.operation_id

    def effect():
        closed = repo.update(
            "alice",
            "fact",
            old["id"],
            {"valid_to": SAID_AT.isoformat(), "superseded_by": new["id"]},
            expected_revision=old["revision"],
            operation_id=operation + ":explicit-change:close",
        )
        opened = repo.update(
            "alice",
            "fact",
            new["id"],
            {"valid_from": SAID_AT.isoformat(), "supersedes": old["id"]},
            expected_revision=new["revision"],
            operation_id=operation + ":explicit-change:open",
        )
        change = repo.put(
            "alice",
            "proposal",
            "synthetic-slot-change",
            {
                "kind": "memory2_slot_undo",
                "status": "applied",
                "fact_ids": [old["id"], new["id"]],
                "old_revision": closed["revision"] + change_revision_delta,
                "new_revision": opened["revision"],
            },
            expected_revision=0,
            operation_id=operation + ":explicit-change:change",
        )
        return {
            "write_status": "updated",
            "kind": "fact",
            "id": new["id"],
            "fact_id": new["id"],
            "revision": opened["revision"] if receipt_revision is None else receipt_revision,
            "ids": [change["id"]],
            "affected_ids": [old["id"]],
        }

    receipt = repo.mutation_request("alice", "agent_memory_write", operation, {"synthetic": "slot-update"}, effect)
    result = ToolResult(ok=True, receipt=receipt, summary="合成更新")
    h.journal.complete(step, result.model_dump())
    return h, old, new, result


def test_updated_closes_exact_old_fact_and_reconciles_both_native_versions(repo: PostgresRepository) -> None:
    h, old, new, result = updated(repo)
    versions, records = verified_versions(h.service, h.run, "memory_write", result)
    for row in (old, new):
        assert versions[entity_dependency("fact", row["id"])] == row["revision"] + 1
    reconciled = reconcile_versions(
        repo, h.run, {entity_dependency("fact", row["id"]): row["revision"] for row in (old, new)}
    )
    assert all(value == 2 for value in reconciled.values())
    assert {("fact", old["id"]), ("fact", new["id"])} <= {(row["kind"], row["id"]) for row in records}
    native = persisted_receipts(repo, h.run)
    before = deepcopy(native)
    public = public_receipt(public_updated_receipts(repo, h.run, native)[0])
    assert public["ids"] == ["synthetic-slot-change"]
    assert public["summary"] == "已更新：我喜欢喝茶 → 我现在改喝咖啡，不再喝茶［撤销］"
    assert native == before and "_operation" not in public
    assert public_receipt({"ids": "bad", "reasoning": "private"}) == {}
    h.finish()


@pytest.mark.parametrize("revision", [True, 1, 3])
def test_updated_new_fact_revision_must_be_exact(repo: PostgresRepository, revision: object) -> None:
    h, _, new, result = updated(repo, receipt_revision=revision)
    with pytest.raises(RevisionConflict):
        verified_versions(h.service, h.run, "memory_write", result)
    own = persisted_receipts(repo, h.run)
    with repo.transaction("alice") as connection:
        assert not _own_revision(connection, repo, h.run, repo.get("alice", "fact", new["id"]), "fact", own)
    h.finish()


def test_updated_old_fact_change_proof_must_have_exact_revision(repo: PostgresRepository) -> None:
    h, old, _, result = updated(repo, change_revision_delta=1)
    with pytest.raises(RevisionConflict):
        verified_versions(h.service, h.run, "memory_write", result)
    with pytest.raises(RevisionConflict):
        reconcile_versions(repo, h.run, {entity_dependency("fact", old["id"]): old["revision"]})
    h.finish()


@pytest.mark.parametrize("kind", ["old", "new"])
def test_later_external_revision_cannot_be_adopted_by_old_updated_prefix(repo: PostgresRepository, kind: str) -> None:
    h, old, new, result = updated(repo)
    row = repo.get("alice", "fact", (old if kind == "old" else new)["id"])
    repo.update(
        "alice",
        "fact",
        row["id"],
        {"summary": "外部后续变更"},
        expected_revision=row["revision"],
        operation_id="external-write",
    )
    with pytest.raises(RevisionConflict):
        verified_versions(h.service, h.run, "memory_write", result)
    h.finish()


def test_forged_updated_receipt_without_native_mutation_proof_is_rejected(repo: PostgresRepository) -> None:
    h, _, _, result = updated(repo)
    forged = replace_result(result, affected_ids=["other-owner-or-invented"])
    with pytest.raises(CoreError):
        verified_versions(h.service, h.run, "memory_write", forged)
    h.finish()


def test_later_change_record_revision_invalidates_historical_adoption(repo: PostgresRepository) -> None:
    h, old, _, result = updated(repo)
    change = repo.get("alice", "proposal", result.receipt["ids"][0])
    repo.update(
        "alice",
        "proposal",
        change["id"],
        {"external_metadata": True},
        expected_revision=change["revision"],
        operation_id="external-change-record",
    )
    with pytest.raises(RevisionConflict):
        reconcile_versions(repo, h.run, {entity_dependency("fact", old["id"]): old["revision"]})
    h.finish()


def replace_result(result: ToolResult, **changes) -> ToolResult:
    return result.model_copy(update={"receipt": dict(result.receipt, **changes)})


def test_memory_receipt_event_accepts_updated_without_undo_token() -> None:
    event = MemoryReceipt(
        v=1,
        run_id="r",
        seq=1,
        ts="2026-10-27T01:20:00+08:00",
        fact_id="f",
        write_status="updated",
        summary="已更新",
        sensitive=False,
    )
    assert event.write_status == "updated" and event.undo_token is None

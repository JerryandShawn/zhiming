"""Only completed tool receipts for the current exact revision permit frozen replay."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.context import ContextEngine
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.models.port import ChatMessage, StreamEvent, ToolCall
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

from .test_loop_cycle_case_versions_pg import existing_case_with_feedback, selected_run
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare, writer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def prepared_case(repo: PostgresRepository) -> tuple[Any, ...]:
    case, registry = existing_case_with_feedback(repo)
    run = selected_run(repo, case["id"], "目标改成合成复盘")
    frozen = AgentSnapshotStore(repo).load_or_build(
        run,
        lambda: ContextEngine(MemoryService(repo), "合成系统").build(
            "alice", run["request"]["source_message_id"], case_ids=(case["id"],)
        ),
    )
    call = ToolCall(
        "update",
        "case_update",
        {
            "id": case["id"],
            "expected_revision": case["revision"],
            "message_id": run["request"]["source_message_id"],
            "quote": run["request"]["message"],
            "changes": {"goal": "合成复盘"},
        },
    )
    return case, registry, run, frozen, call


def test_own_case_write_continues_and_replays_without_rewriting_frozen_bytes(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    case, registry, run, frozen, call = prepared_case(repo)
    frozen_hash = fingerprint(asdict(frozen))
    port = ScriptedPort([answer("", [call]), answer("合成复盘答复")])
    outcome = cycle(port, registry, run, frozen).execute()
    key = entity_dependency("case", case["id"])
    assert outcome.stop_reason == "completed" and outcome.text == "合成复盘答复"
    assert frozen.injected_versions[key] == 1 and outcome.versions[key] == 2
    restored = AgentSnapshotStore(repo).load_or_build(run, lambda: pytest.fail("不得重建冻结前缀"))
    assert fingerprint(asdict(restored)) == frozen_hash
    replay_port = ScriptedPort([])
    replay = cycle(replay_port, registry, run, restored).execute()
    assert replay.stop_reason == "completed" and replay.text == outcome.text
    assert replay.receipts == outcome.receipts and replay_port.requests == []
    assert repo.get("alice", "case", case["id"])["revision"] == 2


def test_model_step_after_selected_feedback_has_valid_journal_identity(cycle_repo: PostgresRepository) -> None:
    _, registry, run, frozen, _ = prepared_case(cycle_repo)
    component = cycle(ScriptedPort([answer("合成首步")]), registry, run, frozen)
    response = component._model()
    assert response.text == "合成首步"


def test_external_new_revision_cannot_reuse_old_own_operation(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    case, registry, run, frozen, call = prepared_case(repo)

    class ExternalWriterPort(ScriptedPort):
        def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
            if self.requests:
                current = repo.get("alice", "case", case["id"])
                repo.update(
                    "alice", "case", case["id"], {"title": "外部合成修订"}, expected_revision=current["revision"]
                )
            yield from super().stream(messages, **kwargs)

    port = ExternalWriterPort([answer("", [call]), answer("不得采用的答复")])
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "lease_or_source_invalid"
    assert outcome.text != "不得采用的答复"
    with pytest.raises(RevisionConflict):
        AgentSnapshotStore(repo).load_or_build(run, lambda: pytest.fail("不得重建快照"))


@pytest.mark.parametrize("proof", ["completed_step", "operation", "mutation_receipt"])
def test_missing_persisted_proof_rejects_same_epoch_replay(cycle_repo: PostgresRepository, proof: str) -> None:
    repo = cycle_repo
    case, registry, run, frozen, call = prepared_case(repo)
    outcome = cycle(ScriptedPort([answer("", [call]), answer("已更新")]), registry, run, frozen).execute()
    assert outcome.stop_reason == "completed"
    with repo.transaction("alice") as connection:
        if proof == "completed_step":
            connection.execute(
                sql.SQL("UPDATE {} SET status='started' WHERE owner=%s AND run_id=%s AND name='case_update'").format(
                    repo.table("core_run_steps")
                ),
                ("alice", run["id"]),
            )
        elif proof == "operation":
            connection.execute(
                sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='case' AND result_id=%s").format(
                    repo.table("core_operations")
                ),
                ("alice", case["id"]),
            )
        else:
            connection.execute(
                sql.SQL(
                    "DELETE FROM {} WHERE owner=%s AND operation='agent_case_update' AND request_key LIKE %s"
                ).format(repo.table("core_mutation_requests")),
                ("alice", "run:" + run["id"] + ":%"),
            )
    with pytest.raises(RevisionConflict if proof != "mutation_receipt" else EvidenceError):
        AgentSnapshotStore(repo).load_or_build(run, lambda: pytest.fail("不得重建快照"))


def test_new_write_external_revision_before_dependency_registration_is_rejected(
    cycle_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    actual = registry.execute
    written_revisions: list[int] = []

    def concurrent_revision(name: str, arguments: dict[str, Any], context: Any) -> Any:
        result = actual(name, arguments, context)
        receipt = result.receipt
        assert receipt and receipt["write_status"] == "saved"
        written_revisions.append(receipt["revision"])
        repo.update("alice", "fact", receipt["id"], {"synthetic_metadata": True}, expected_revision=receipt["revision"])
        return result

    monkeypatch.setattr(registry, "execute", concurrent_revision)
    port = ScriptedPort([answer("", [ToolCall("write", "memory_write", writer(run))]), answer("不得继续")])
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "lease_or_dependency_invalid" and len(port.requests) == 1
    fact = repo.list("alice", "fact")[0]
    assert fact["revision"] == written_revisions[0] + 1
    assert "fact:" + fact["id"] not in repo.fetch_run("alice", run["id"])["state_version"]

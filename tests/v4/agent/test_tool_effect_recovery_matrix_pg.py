"""Real Runtime/PG effects survive one missing Journal acknowledgement unchanged."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from mingjing_core.application.agent_commit_versions import persisted_receipts
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_agent_runtime_pg import invoke
from .test_loop_cycle_support import ScriptedPort, answer, modify
from .test_loop_cycle_support import cycle_repo as source_fixture
from .tool_effect_recovery_support import (
    TEXTS,
    CrashBeforeAcknowledgement,
    assert_source_binding,
    business_state,
    mutation_row,
    operation_rows,
    prepare_intent,
    step_row,
)


@pytest.fixture
def effects_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("name", [key for key in TEXTS if key != "memory_update"])
def test_effect_committed_before_ack_reclaims_same_epoch_without_second_mutation(
    effects_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    repo, intent = effects_repo, prepare_intent(effects_repo, name)
    original_source = repo.get("alice", "message", intent.run["request"]["source_message_id"])
    crash = CrashBeforeAcknowledgement(repo, intent.name, monkeypatch)
    first = ScriptedPort([answer("", [ToolCall("effect", intent.name, intent.arguments)])])
    with pytest.raises(SystemExit, match="synthetic-effect-committed-before-journal-ack"):
        invoke(repo, intent.run, first)
    assert crash.count == 1 and crash.step is not None and crash.output is not None
    step, output = crash.step, crash.output
    before, mutation, operations = business_state(repo), mutation_row(repo, step), operation_rows(repo, step)
    assert mutation["receipt"] == output["receipt"] and operations
    assert step_row(repo, step)["status"] == "started" and step_row(repo, step)["output"] is None
    assert_source_binding(repo, intent, output["receipt"])
    modify(repo, intent.run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", intent.run["id"], lease_seconds=150)
    assert reclaimed["retry_epoch"] == step.epoch == intent.run["retry_epoch"]
    assert reclaimed["lease_token"] != intent.run["lease_token"]
    resumed = ScriptedPort([answer("恢复后的合成回答。")])
    result, events = invoke(repo, reclaimed, resumed)
    after = repo.fetch_run("alice", reclaimed["id"])
    assert after["status"] == "succeeded" and after["retry_epoch"] == step.epoch
    assert result["text"] == "恢复后的合成回答。" and len(resumed.requests) == len(first.requests) == 1
    assert result["usage"]["replayed_model_steps"] == 1 and result["usage"]["model_streams_this_execution"] == 1
    assert business_state(repo) == before and mutation_row(repo, step) == mutation
    assert operation_rows(repo, step) == operations and crash.count == 1
    assert step_row(repo, step)["status"] == "completed" and step_row(repo, step)["output"] == output
    proof = next(item for item in persisted_receipts(repo, after) if item["_operation"] == step.operation_id)
    assert {key: value for key, value in proof.items() if key != "_operation"} == output["receipt"]
    assert repo.get("alice", "message", original_source["id"]) == original_source
    assert sum(row.get("role") == "assistant" for row in repo.list("alice", "message")) == 1
    assert sum(event["type"] == "final" for event in events) == 1


def test_real_memory_correction_invalidates_old_epoch_without_duplicate_or_lost_receipt(
    effects_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, intent = effects_repo, prepare_intent(effects_repo, "memory_update")
    crash = CrashBeforeAcknowledgement(repo, intent.name, monkeypatch)
    first = ScriptedPort([answer("", [ToolCall("correct", intent.name, intent.arguments)])])
    with pytest.raises(SystemExit, match="synthetic-effect-committed-before-journal-ack"):
        invoke(repo, intent.run, first)
    assert crash.count == 1 and crash.step is not None and crash.output is not None
    step, output = crash.step, crash.output
    stored = repo.fetch_run("alice", intent.run["id"])
    assert stored["status"] == "stale" and stored["retry_epoch"] == step.epoch == 0
    assert stored["lease_token"] is None and stored["result"] is None
    assert repo.get("alice", "fact", intent.old["id"])["status"] == "superseded"
    assert_source_binding(repo, intent, output["receipt"])
    before, mutation, operations = business_state(repo), mutation_row(repo, step), operation_rows(repo, step)
    assert mutation["receipt"] == output["receipt"] and len(before["fact"]) == 2
    assert step_row(repo, step)["status"] == "started" and step_row(repo, step)["output"] is None
    denied = ScriptedPort([])
    with pytest.raises(CoreError):
        invoke(repo, intent.run, denied)
    assert denied.requests == [] and len(first.requests) == 1
    assert business_state(repo) == before and mutation_row(repo, step) == mutation
    assert operation_rows(repo, step) == operations and crash.count == 1
    assert repo.fetch_run("alice", intent.run["id"])["retry_epoch"] == 0
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]

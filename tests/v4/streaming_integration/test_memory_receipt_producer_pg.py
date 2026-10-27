"""Unrun M4c acceptance examples; memory effects and acknowledgements remain real PG."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.events import validate_event
from mingjing_core.application import agent_runtime_events
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from tests.v4.agent.test_agent_runtime_pg import queued
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, modify, writer
from tests.v4.agent.test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="receipt_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def execute(
    repo: PostgresRepository,
    run: dict[str, Any],
    port: ScriptedPort,
    callback: Callable[[dict], None] | None = None,
    *,
    candidate: bool = True,
) -> dict:
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, streaming_candidate=candidate)
    return runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], callback)


def script(run: dict[str, Any]) -> ScriptedPort:
    arguments = dict(writer(run), summary="模型摘要不能作为公开回执文案")
    return ScriptedPort([answer("", [ToolCall("write", "memory_write", arguments)]), answer("已处理这一步")])


def receipts(repo: PostgresRepository, run: dict[str, Any]) -> list[dict]:
    with repo.pool.connection() as connection:
        return connection.execute(
            sql.SQL(
                "SELECT seq,payload FROM {} WHERE owner=%s AND run_id=%s AND kind='memory_receipt' ORDER BY seq"
            ).format(repo.table("core_run_events")),
            ("alice", run["id"]),
        ).fetchall()


def committed_proof(repo: PostgresRepository, run: dict[str, Any]) -> dict:
    # A separate pool connection does not reuse the producer transaction or its owner lock.
    with repo.pool.connection() as connection:
        step = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND kind='tool' AND name='memory_write'"
            ).format(repo.table("core_run_steps")),
            ("alice", run["id"], run["retry_epoch"]),
        ).fetchone()
        operation = f"run:{run['id']}:e{run['retry_epoch']}:s{step['seq']}" if step else None
        mutation = connection.execute(
            sql.SQL("SELECT receipt FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
                repo.table("core_mutation_requests")
            ),
            ("alice", "agent_memory_write", operation),
        ).fetchone()
        count = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s AND run_id=%s AND kind='memory_receipt'").format(
                repo.table("core_run_events")
            ),
            ("alice", run["id"]),
        ).fetchone()["n"]
    return {"step": step, "mutation": mutation, "events": count}


@pytest.mark.parametrize(
    "text,kind,state,sensitive",
    [("我喜欢合成夜班", "fact", "saved", False), ("我确诊了合成焦虑症", "proposal", "pending_confirm", True)],
)
def test_actual_memory_effect_emits_exact_fact_or_proposal_without_private_body(
    receipt_repo: PostgresRepository, text: str, kind: str, state: str, sensitive: bool
) -> None:
    repo, public = receipt_repo, []
    run = queued(repo, text)
    result = execute(repo, run, script(run), public.append)
    assert result["schema"] == "core4.0"
    entities, events = repo.list("alice", kind), receipts(repo, run)
    assert len(entities) == len(events) == 1
    payload = validate_event("memory_receipt", events[0]["payload"])
    identity = "fact_id" if kind == "fact" else "proposal_id"
    other = "proposal_id" if kind == "fact" else "fact_id"
    assert payload[identity] == entities[0]["id"] and payload.get(other) is None
    assert payload["write_status"] == state and payload["sensitive"] is sensitive
    assert payload.get("undo_token") is None
    assert text not in json.dumps(payload, ensure_ascii=False)
    assert "模型摘要不能作为公开回执文案" not in payload["summary"]
    assert sum(event["type"] == "memory_receipt" for event in public) == 1


def test_callback_observes_real_completed_journal_mutation_and_event_after_outer_commit(
    receipt_repo: PostgresRepository,
) -> None:
    repo, observations = receipt_repo, []
    run = queued(repo)

    def callback(event: dict) -> None:
        if event["type"] == "memory_receipt":
            observations.append(committed_proof(repo, run))

    execute(repo, run, script(run), callback)
    assert len(observations) == 1
    proof = observations[0]
    assert proof["step"]["status"] == "completed" and proof["step"]["finished_at"] is not None
    assert proof["mutation"]["receipt"] == proof["step"]["output"]["receipt"] and proof["events"] == 1


def test_event_append_failure_rolls_back_journal_ack_event_and_operation_but_keeps_one_real_effect(
    receipt_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, callback_events = receipt_repo, []
    run, original = queued(repo), agent_runtime_events.append_event

    def crash(*args: Any, **kwargs: Any) -> dict:
        event = original(*args, **kwargs)
        if event["type"] == "memory_receipt":
            raise SystemExit("synthetic receipt append interruption")
        return event

    monkeypatch.setattr(agent_runtime_events, "append_event", crash)
    with pytest.raises(SystemExit, match="synthetic receipt append interruption"):
        execute(repo, run, script(run), callback_events.append)
    proof = committed_proof(repo, run)
    assert proof["mutation"] is not None and len(repo.list("alice", "fact")) == 1
    assert proof["step"]["status"] == "started" and proof["step"]["output"] is None
    assert proof["step"]["finished_at"] is None and proof["events"] == 0
    assert not any(event["type"] == "memory_receipt" for event in callback_events)
    step = proof["step"]
    operation = f"p4-event:{run['id']}:e{run['retry_epoch']}:memory_receipt:v1:s{step['seq']}:{step['input_fp']}"
    with repo.pool.connection() as connection:
        row = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {} WHERE owner=%s AND operation_id=%s AND kind='run_event_v1'").format(
                repo.table("core_operations")
            ),
            ("alice", operation),
        ).fetchone()
    assert row["n"] == 0


def test_completed_tool_replay_keeps_original_receipt_seq_and_never_requests_model_again(
    receipt_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, run = receipt_repo, queued(receipt_repo)
    original = AgentFinalizer.finalize

    def crash(*args: Any, **kwargs: Any) -> dict:
        raise SystemExit("synthetic interruption before final commit")

    monkeypatch.setattr(AgentFinalizer, "finalize", crash)
    with pytest.raises(SystemExit):
        execute(repo, run, script(run))
    before = receipts(repo, run)
    assert len(before) == 1
    monkeypatch.setattr(AgentFinalizer, "finalize", original)
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    port = ScriptedPort([])
    result = execute(repo, reclaimed, port)
    assert result["schema"] == "core4.0" and port.requests == []
    assert receipts(repo, reclaimed) == before and len(repo.list("alice", "fact")) == 1


@pytest.mark.parametrize("text", ["我的密码是合成示例", "不要保存我喜欢合成夜班"])
def test_no_entity_rejection_never_fabricates_a_public_memory_identifier(
    receipt_repo: PostgresRepository, text: str
) -> None:
    repo, public = receipt_repo, []
    run = queued(repo, text)
    execute(repo, run, script(run), public.append)
    assert repo.list("alice", "fact") == repo.list("alice", "proposal") == []
    assert receipts(repo, run) == [] and not any(event["type"] == "memory_receipt" for event in public)


def test_default_runtime_without_trusted_p4_hook_preserves_existing_generic_events(
    receipt_repo: PostgresRepository,
) -> None:
    repo, public = receipt_repo, []
    run = queued(repo)
    execute(repo, run, script(run), public.append, candidate=False)
    assert len(repo.list("alice", "fact")) == 1 and receipts(repo, run) == []
    assert any(event["type"] == "tool_result" for event in public)

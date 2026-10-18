"""Scripted model plus registered real-PG read/write tools; no RuntimePort or commit claim."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.agent.context_types import BudgetPolicy
from mingjing_core.agent.toolkit import ToolRegistry
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import ScriptedPort, answer, cycle, modify, prepare, writer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_read_write_continue_replays_complete_reasoning_and_registers_real_effects(
    cycle_repo: PostgresRepository,
) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    port = ScriptedPort(
        [
            answer("", [ToolCall("read", "time_context", {})]),
            answer("", [ToolCall("write", "memory_write", writer(run))]),
            answer("合成答复〔f1〕"),
        ]
    )
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "completed" and result.text == "合成答复〔f1〕"
    fact = repo.list("alice", "fact")[0]
    assert fact["content"] == run["request"]["message"] and len(repo.list("alice", "fact")) == 1
    assert result.receipts[0]["id"] == fact["id"] and result.alias_map["f1"]["id"] == fact["id"]
    assert result.versions["fact:" + fact["id"]] == fact["revision"]
    assert "fact:" + fact["id"] not in frozen.injected_versions
    assert result.usage["model_steps"] == 3 and result.usage["model_streams_this_execution"] == 3
    assert result.usage["reported_tokens"]["cache_read_tokens"] == 15
    assert result.usage["reported_tokens"]["cache_write_tokens"] == 12
    for request in port.requests[1:]:
        assistants = [message for message in request["messages"] if message.role == "assistant"]
        assert assistants and all(
            message.reasoning == "合成受控推理" and message.reasoning_signature == "合成签名" for message in assistants
        )
        assert all(message.tool_cycle == run["id"] + ":e0" for message in assistants)
    assert [message.tool_call_id for message in port.requests[-1]["messages"] if message.role == "tool"] == [
        "read",
        "write",
    ]
    assert all(request["tool_choice"] == "auto" for request in port.requests)
    assert repo.fetch_run("alice", run["id"])["status"] == "running"  # The component does not finalize/commit.


def test_completed_cycle_after_repository_reopen_never_calls_provider_or_repeats_mutation(
    cycle_repo: PostgresRepository,
) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    first = cycle(
        ScriptedPort([answer("", [ToolCall("w", "memory_write", writer(run))]), answer("原回答")]),
        registry,
        run,
        frozen,
    ).execute()
    revision = repo.get_revision("alice")
    reopened = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        replay_registry = ToolRegistry(AgentToolsService(reopened))
        restored = AgentSnapshotStore(reopened).load_or_build(run, lambda: pytest.fail("不得重建首请求"))
        port = ScriptedPort([])
        replay = cycle(port, replay_registry, run, restored).execute()
        assert port.requests == [] and replay.text == first.text and replay.receipts == first.receipts
        assert replay.versions == first.versions and replay.alias_map == first.alias_map
        assert replay.usage["model_streams_this_execution"] == 0 and replay.usage["replayed_model_steps"] == 2
    finally:
        reopened.close()
    assert repo.get_revision("alice") == revision and len(repo.list("alice", "fact")) == 1


def test_crash_after_physical_tool_effect_recovers_same_operation_without_duplicate(
    cycle_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    actual = registry.execute

    def crashing(name: str, arguments: dict[str, Any], ctx: Any) -> Any:
        actual(name, arguments, ctx)
        raise SystemExit("synthetic crash after committed database effect")

    monkeypatch.setattr(registry, "execute", crashing)
    with pytest.raises(SystemExit):
        cycle(ScriptedPort([answer("", [ToolCall("w", "memory_write", writer(run))])]), registry, run, frozen).execute()
    fact = repo.list("alice", "fact")[0]
    revision = fact["revision"]
    monkeypatch.setattr(registry, "execute", actual)
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=3600)
    frozen_again = AgentSnapshotStore(repo).load_or_build(reclaimed, lambda: pytest.fail("不得重建首请求"))
    port = ScriptedPort([answer("恢复完成")])
    result = cycle(port, registry, reclaimed, frozen_again).execute()
    assert result.text == "恢复完成" and len(port.requests) == 1
    assert len(repo.list("alice", "fact")) == 1 and repo.get("alice", "fact", fact["id"])["revision"] == revision
    with repo.transaction("alice") as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE operation='agent_memory_write'").format(
                repo.table("core_mutation_requests")
            )
        ).fetchone()["count"]
    assert count == 1 and len(result.receipts) == 1


def test_ask_user_ends_turn_and_remaining_calls_get_paired_rejections(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    question = {
        "question": "你更在意什么？",
        "options": ["时间", "收入"],
        "allow_free_text": True,
        "why": "答案会影响建议",
        "slot": "最在意因素",
        "changes_conclusion": "影响建议顺序",
    }
    port = ScriptedPort(
        [answer("", [ToolCall("ask", "ask_user", question), ToolCall("never", "memory_write", writer(run))])]
    )
    component = cycle(port, registry, run, frozen)
    result = component.execute()
    assert result.stop_reason == "asked" and result.asked["question"] == question["question"]
    assert repo.list("alice", "fact") == [] and len(port.requests) == 1
    tools = [message for message in component.messages if message.role == "tool"]
    assert [message.tool_call_id for message in tools] == ["ask", "never"]
    assert json.loads(tools[-1].content)["data"]["code"] == "turn_ended"
    replay = cycle(
        ScriptedPort([]), registry, run, AgentSnapshotStore(repo).load_or_build(run, lambda: pytest.fail())
    ).execute()
    assert (
        replay.asked == result.asked
        and repo.get("alice", "thread", "life:self")["clarify_slots"][0]["asked_count"] == 1
    )


def test_new_user_round_contains_only_old_thread_text_not_old_reasoning(cycle_repo: PostgresRepository) -> None:
    repo = cycle_repo
    run, registry, frozen = prepare(repo)
    first = cycle(
        ScriptedPort([answer("", [ToolCall("read", "time_context", {})]), answer("旧轮合成回答")]),
        registry,
        run,
        frozen,
    ).execute()
    MemoryService(repo).record_assistant_message(
        "alice",
        "self",
        "life:self",
        first.text,
        run_id=run["id"],
        channel="web",
        source_ids=[run["request"]["source_message_id"]],
    )
    newer, next_registry, next_frozen = prepare(repo, "下一轮合成问题")
    port = ScriptedPort([answer("新轮回答")])
    assert cycle(port, next_registry, newer, next_frozen).execute().text == "新轮回答"
    assert any(message.content.find("旧轮合成回答") >= 0 for message in port.requests[0]["messages"])
    assert all(
        not message.reasoning and not message.reasoning_signature and not message.tool_calls
        for message in port.requests[0]["messages"]
    )


def test_remote_tool_source_is_registered_for_withdrawal_cleanup(cycle_repo: PostgresRepository) -> None:
    repo, memory = cycle_repo, MemoryService(cycle_repo)
    old = memory.receive("alice", content="我喜欢合成考研", source_id="remote", at=get_clock().now())
    for index in range(3):
        memory.receive("alice", content="中间合成消息", source_id=str(index), at=get_clock().now())
    run, registry, frozen = prepare(repo, "当前普通问题", policy=BudgetPolicy(history_limit=2))
    assert "message:" + old["id"] not in frozen.injected_versions
    port = ScriptedPort(
        [
            answer("", [ToolCall("find", "memory_search", {"query": "考研", "kinds": ["message"]})]),
            answer("找到合成旧消息"),
        ]
    )
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "completed" and "message:" + old["id"] in result.versions
    fact = memory.save_fact("alice", "self", old["id"], old["content"], "preference")
    memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    assert repo.fetch_run("alice", run["id"])["status"] == "revoked"
    assert all(row["status"] == "deleted" for row in repo.list("alice", "runtime_step", include_deleted=True))

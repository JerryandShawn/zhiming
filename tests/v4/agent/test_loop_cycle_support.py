"""Explicit offline scripted transport; PostgreSQL remains the real authority."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_budget import count_request
from mingjing_core.agent.context_tokens import TokenReading
from mingjing_core.agent.context_types import ContextBuild
from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_cycle import LoopCycle
from mingjing_core.agent.toolkit import ToolContext, ToolRegistry
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import AssistantMessage, ChatMessage, ModelPort, StreamEvent, ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock


@pytest.fixture
def cycle_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("循环集成测试禁止外部HTTP/子进程")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    old = get_clock()
    set_clock(FrozenClock(datetime(2026, 10, 18, 12, tzinfo=UTC)))
    try:
        yield p2_repo
    finally:
        set_clock(old)


class SyntheticMeter:
    version = "synthetic_serialized_policy_units_only_v1"
    provider = "scripted"
    model = "synthetic"
    live_admissible = False

    def measure(self, messages: Any, tools: Any, *, tool_choice: str) -> TokenReading:
        return TokenReading(None, count_request(messages, tools, tool_choice=tool_choice).serialized_bytes)


class ScriptedPort(ModelPort):
    offline = True

    def __init__(self, responses: list[AssistantMessage]) -> None:
        self.responses, self.requests = responses, []

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.requests.append(
            {
                "messages": copy.deepcopy(messages),
                **copy.deepcopy({key: value for key, value in kwargs.items() if key != "cancel_event"}),
            }
        )
        response = self.responses[len(self.requests) - 1]
        if response.reasoning:
            yield StreamEvent("reasoning", response.reasoning)
        if response.text:
            yield StreamEvent("text", response.text)
        for call in response.tool_calls:
            yield StreamEvent("tool_call", call)
        yield StreamEvent("usage", response.usage)
        yield StreamEvent(
            "done",
            {
                "model": "scripted-loop-component",
                "provider": "scripted",
                "reasoning_signature": response.reasoning_signature,
            },
        )


def answer(
    text: str = "合成回答", calls: list[ToolCall] | None = None, *, reasoning: str = "合成受控推理"
) -> AssistantMessage:
    return AssistantMessage(
        text=text,
        tool_calls=calls or [],
        reasoning=reasoning,
        reasoning_signature="合成签名",
        usage={"input_tokens": 17, "output_tokens": 3, "cache_read_tokens": 5, "cache_write_tokens": 4},
    )


def prepare(
    repo: PostgresRepository, text: str = "我喜欢合成夜班", **context_options: Any
) -> tuple[dict, ToolRegistry, ContextBuild]:
    source = MemoryService(repo).receive("alice", content=text, source_id=uuid.uuid4().hex, at=get_clock().now())
    run = repo.queue_run(
        "alice", uuid.uuid4().hex, {"message": text, "source_message_id": source["id"], "case_ids": []}
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    run = repo.claim_run("alice", run["id"], lease_seconds=3600)
    registry = ToolRegistry(AgentToolsService(repo))
    ctx = ToolContext("alice", run["id"], "self", 0, 1, run["lease_token"], "model", "0" * 64, "life:self")
    engine = ContextEngine(MemoryService(repo), "合成循环测试系统", clock=get_clock(), **context_options)
    frozen = AgentSnapshotStore(repo).load_or_build(
        run, lambda: engine.build("alice", source["id"], tools=tuple(registry.specs(ctx)))
    )
    return run, registry, frozen


def cycle(port: ModelPort, registry: ToolRegistry, run: dict, frozen: ContextBuild, **kwargs: Any) -> LoopCycle:
    return LoopCycle(
        port,
        registry,
        Journal(registry.service.repo, "alice"),
        run,
        frozen,
        token_meter=SyntheticMeter(),
        offline=True,
        **kwargs,
    )


def modify(repo: PostgresRepository, run: dict[str, Any], clause: str) -> None:
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET {} WHERE owner=%s AND id=%s").format(repo.table("core_runs"), sql.SQL(clause)),
            ("alice", run["id"]),
        )


def writer(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": run["request"]["source_message_id"],
        "quote": run["request"]["message"],
        "kind": "preference",
        "summary": "合成普通偏好",
    }

"""Real PG controls with explicit offline ports: limits, cancellation and meter refusal."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_cycle import LoopCycle
from mingjing_core.agent.loop_policy import LoopPolicy, RunControl
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.port import ChatMessage, StreamEvent, ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, cycle, modify, prepare, writer
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="cycle_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_empty_response_falls_back_to_nonempty_text(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    result = cycle(ScriptedPort([answer("")]), registry, run, frozen).execute()
    assert result.text.strip() and result.stop_reason == "empty_answer"


def test_third_identical_normalized_tool_is_rejected_before_effect(
    cycle_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, registry, frozen = prepare(cycle_repo)
    real, executed = registry.execute, []

    def observe(name: str, arguments: dict[str, Any], ctx: Any) -> Any:
        executed.append(name)
        return real(name, arguments, ctx)

    monkeypatch.setattr(registry, "execute", observe)
    replies = [
        answer("", [ToolCall(str(index), "time_context", {} if index != 1 else {"date": None})]) for index in range(3)
    ]
    port = ScriptedPort(replies)
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "repeated_tool" and result.text.strip()
    assert executed == ["time_context", "time_context"] and len(port.requests) == 3


def test_per_step_tool_limit_has_zero_physical_tool_effects(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    calls = [ToolCall(str(index), "memory_write", writer(run)) for index in range(7)]
    port = ScriptedPort([answer("", calls)])
    result = cycle(port, registry, run, frozen).execute()
    assert result.stop_reason == "step_tool_limit" and cycle_repo.list("alice", "fact") == []
    assert len(port.requests) == 1


def test_iteration_limit_stops_without_extra_model_request(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    port = ScriptedPort(
        [answer("", [ToolCall(str(index), "time_context", {"date": f"2026-10-{17 + index}"})]) for index in range(2)]
    )
    result = cycle(port, registry, run, frozen, policy=LoopPolicy(max_iterations=2)).execute()
    assert result.stop_reason == "iteration_limit" and len(port.requests) == 2 and result.text.strip()


@pytest.mark.parametrize(
    "options",
    [
        {"max_iterations": 41},
        {"max_seconds": 481},
        {"max_tools": 7},
        {"repeat_limit": 4},
        {"max_iterations": True},
        {"only_tool": "time_context", "text_only": True},
    ],
)
def test_policy_cannot_expand_approved_limits(options: dict[str, Any]) -> None:
    with pytest.raises(EvidenceError):
        LoopPolicy(**options)
    assert (LoopPolicy().iterations, LoopPolicy().seconds, LoopPolicy().tools_per_step) == (40, 480, 6)
    assert (
        LoopPolicy(depth="deep").iterations,
        LoopPolicy(depth="deep").seconds,
        LoopPolicy(depth="deep").tools_per_step,
    ) == (60, 1200, 10)


@pytest.mark.parametrize("mode", ["unknown_meter", "live_with_synthetic", "non_scripted_offline"])
def test_unverified_meter_or_offline_mislabel_prevents_any_provider_call(
    cycle_repo: PostgresRepository, mode: str
) -> None:
    run, registry, frozen = prepare(cycle_repo)
    port = ScriptedPort([answer()])
    if mode == "non_scripted_offline":
        port.offline = False
    component = LoopCycle(
        port,
        registry,
        Journal(cycle_repo, "alice"),
        run,
        frozen,
        token_meter=None if mode == "unknown_meter" else SyntheticMeter(),
        offline=mode != "live_with_synthetic",
    )
    with pytest.raises(InputMeterUnverified):
        component.execute()
    assert port.requests == [] and cycle_repo.list("alice", "fact") == []


def test_required_first_step_only_exposes_one_tool_then_returns_to_auto(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    port = ScriptedPort([answer("", [ToolCall("first", "time_context", {})]), answer("完成")])
    result = cycle(port, registry, run, frozen, policy=LoopPolicy(only_tool="time_context")).execute()
    assert result.stop_reason == "completed"
    assert [tool.name for tool in port.requests[0]["tools"]] == ["time_context"]
    assert port.requests[0]["tool_choice"] == "required" and port.requests[1]["tool_choice"] == "auto"


def test_text_only_request_cannot_execute_unexposed_tool(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    port = ScriptedPort([answer("", [ToolCall("never", "memory_write", writer(run))]), answer("只给文字")])
    result = cycle(port, registry, run, frozen, policy=LoopPolicy(text_only=True)).execute()
    assert result.stop_reason == "completed" and cycle_repo.list("alice", "fact") == []
    assert all(request["tools"] == [] and request["tool_choice"] == "auto" for request in port.requests)


def test_monotonic_wall_limit_does_not_depend_on_frozen_business_clock(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)
    elapsed = [0.0]
    policy = LoopPolicy(max_seconds=1)
    control = RunControl(cycle_repo, run, policy, monotonic=lambda: elapsed[0])

    class LatePort(ScriptedPort):
        def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
            elapsed[0] = 2.0
            yield from super().stream(messages, **kwargs)

    port = LatePort([answer("迟到内容")])
    result = cycle(port, registry, run, frozen, policy=policy, control=control).execute()
    assert result.stop_reason == "wall_time_limit" and len(port.requests) == 1


def test_pg_renewal_occurs_during_stream_fragments(
    cycle_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, registry, frozen = prepare(cycle_repo)
    elapsed = [0.0]
    control = RunControl(cycle_repo, run, LoopPolicy(), monotonic=lambda: elapsed[0])
    real, renewals = cycle_repo.renew_run, []

    def renew(*args: Any, **kwargs: Any) -> Any:
        renewals.append(args[-1])
        return real(*args, **kwargs)

    monkeypatch.setattr(cycle_repo, "renew_run", renew)

    class FragmentPort(ScriptedPort):
        def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
            for stamp in (21.0, 42.0):
                elapsed[0] = stamp
                yield StreamEvent("text", "合成分片")
            yield StreamEvent("done", {})

    result = cycle(FragmentPort([]), registry, run, frozen, control=control).execute()
    assert result.text == "合成分片合成分片" and renewals == [150, 150]


def test_default_pg_monitor_cancels_cooperative_idle_stream_within_two_seconds(cycle_repo: PostgresRepository) -> None:
    run, registry, frozen = prepare(cycle_repo)

    class WaitingPort(ScriptedPort):
        def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
            yield StreamEvent("text", "已生成合成片段")
            modify(cycle_repo, run, "cancel_requested_at=now()")
            assert kwargs["cancel_event"].wait(timeout=2), "PG取消监视器未发停止信号"
            yield StreamEvent("done", {})

    started = time.monotonic()
    result = cycle(WaitingPort([]), registry, run, frozen).execute()
    assert result.stop_reason == "cancelled" and time.monotonic() - started < 2
    assert result.text == "已生成合成片段"

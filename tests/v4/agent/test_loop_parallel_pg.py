"""Independent pure handlers overlap while PG journals and results stay ordered."""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest

from mingjing_core.agent.loop_batch import ToolBatch
from mingjing_core.application import agent_tools_reads
from mingjing_core.models.port import ToolCall

from .parallel_tools_support import clocks, tool_rows
from .parallel_tools_support import parallel_repo as source_repo_fixture
from .test_loop_cycle_support import ScriptedPort, answer, cycle, prepare, writer


@pytest.fixture(name="parallel_repo")
def repository_fixture(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def test_real_calendar_computations_overlap_and_reverse_completion_is_reordered(
    parallel_repo: Any, monkeypatch: Any
) -> None:
    repo = parallel_repo
    run, registry, frozen = prepare(repo)
    rendezvous, second_done = threading.Barrier(2), threading.Event()
    actual, observed = agent_tools_reads.almanac, []

    def compute(at: Any, zone: str) -> Any:
        assert getattr(repo._local, "connection", None) is None
        observed.append(threading.current_thread().name)
        rendezvous.wait(timeout=3)
        if at.day == 17:
            assert second_done.wait(3)
        result = actual(at, zone)
        if at.day == 18:
            second_done.set()
        return result

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    port = ScriptedPort([answer("", clocks(17, 18)), answer("已核对")])
    events = []
    component = cycle(port, registry, run, frozen, emit=lambda kind, data: events.append((kind, data)))
    outcome = component.execute()
    messages = [message for message in component.messages if message.role == "tool"]
    assert outcome.stop_reason == "completed" and len(set(observed)) == 2
    assert all(name.startswith("agent-pure-read") for name in observed)
    assert [message.tool_call_id for message in messages] == ["clock-0", "clock-1"]
    assert [json.loads(message.content)["data"]["at"][:10] for message in messages] == ["2026-10-17", "2026-10-18"]
    assert [data["call_id"] for kind, data in events if kind == "tool_result"] == ["clock-0", "clock-1"]
    assert [row["seq"] for row in tool_rows(repo, run)] == [2, 3]


def test_worker_pool_is_bounded_at_two_for_three_pure_calls(parallel_repo: Any, monkeypatch: Any) -> None:
    repo = parallel_repo
    run, registry, frozen = prepare(repo)
    actual, lock, both = agent_tools_reads.almanac, threading.Lock(), threading.Event()
    active, maximum, workers = [0], [0], set()

    def compute(*args: Any, **kwargs: Any) -> Any:
        with lock:
            active[0] += 1
            maximum[0] = max(maximum[0], active[0])
            workers.add(threading.current_thread().ident)
            if active[0] == 2:
                both.set()
        try:
            assert both.wait(3)
            return actual(*args, **kwargs)
        finally:
            with lock:
                active[0] -= 1

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    outcome = cycle(ScriptedPort([answer("", clocks(17, 18, 19)), answer()]), registry, run, frozen).execute()
    assert outcome.stop_reason == "completed" and maximum[0] == 2 and len(workers) == 2


def test_writes_are_barriers_between_pure_reads(parallel_repo: Any, monkeypatch: Any) -> None:
    run, registry, frozen = prepare(parallel_repo)
    actual, save, order = agent_tools_reads.almanac, registry.service.memory.save_fact, []

    def compute(at: Any, zone: str) -> Any:
        order.append(str(at.day))
        return actual(at, zone)

    def save_fact(*args: Any, **kwargs: Any) -> Any:
        order.append("write")
        return save(*args, **kwargs)

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    monkeypatch.setattr(registry.service.memory, "save_fact", save_fact)
    calls = [clocks(17)[0], ToolCall("write", "memory_write", writer(run)), clocks(18)[0]]
    calls[-1] = ToolCall("last", calls[-1].name, calls[-1].arguments)
    port = ScriptedPort([answer("", calls), answer("已保存〔f1〕")])
    outcome = cycle(port, registry, run, frozen).execute()
    assert outcome.stop_reason == "completed" and order == ["17", "write", "18"]
    assert len(parallel_repo.list("alice", "fact")) == 1


def test_repeated_pure_calls_stop_later_calls_before_execution(parallel_repo: Any, monkeypatch: Any) -> None:
    repo = parallel_repo
    run, registry, frozen = prepare(repo)
    actual, calls = agent_tools_reads.almanac, []

    def compute(at: Any, zone: str) -> Any:
        calls.append(at.day)
        return actual(at, zone)

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    port = ScriptedPort([answer("", clocks(17, 17, 17, 18))])
    outcome = cycle(port, registry, run, frozen).execute()
    rows = tool_rows(repo, run)
    assert outcome.stop_reason == "repeated_tool" and calls == [17, 17] and len(port.requests) == 1
    assert rows[2]["output"]["data"]["code"] == "repeated_tool"
    assert rows[3]["output"]["data"]["code"] == "turn_ended"


def test_ask_user_ends_turn_and_later_read_is_not_invoked(parallel_repo: Any, monkeypatch: Any) -> None:
    run, registry, frozen = prepare(parallel_repo)
    actual, observed = agent_tools_reads.almanac, []

    def compute(at: Any, zone: str) -> Any:
        observed.append(at.day)
        return actual(at, zone)

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    ask = dict(
        question="更在意哪项？",
        options=["收入", "时间"],
        allow_free_text=True,
        why="影响建议",
        slot="当前重点",
        changes_conclusion="改变优先级",
    )
    calls = [
        *clocks(17, 18),
        ToolCall("ask", "ask_user", ask),
        ToolCall("late", "time_context", {"date": "2026-10-19"}),
    ]
    outcome = cycle(ScriptedPort([answer("", calls)]), registry, run, frozen).execute()
    assert outcome.stop_reason == "asked" and sorted(observed) == [17, 18]
    assert tool_rows(parallel_repo, run)[-1]["output"]["data"]["code"] == "turn_ended"


def test_cached_tarot_and_unexposed_or_alias_dependent_reads_are_never_parallel(parallel_repo: Any) -> None:
    run, registry, frozen = prepare(parallel_repo)
    component = cycle(ScriptedPort([]), registry, run, frozen)
    component.exposed = {"tarot_read", "memory_search", "time_context"}
    batch = ToolBatch(component)
    assert not batch.eligible(ToolCall("tarot", "tarot_read", {"draw_id": "not-authorized"}))
    assert not batch.eligible(ToolCall("profile", "profile_get", {}))
    assert not batch.eligible(ToolCall("search", "memory_search", {"query": "〔f99〕"}))
    assert batch.eligible(clocks(17)[0])

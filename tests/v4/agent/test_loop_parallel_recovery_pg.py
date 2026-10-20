"""Late pure computations cannot publish after cancellation, withdrawal or crash."""

from __future__ import annotations

import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.application import agent_tools_reads
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError

from .parallel_tools_support import CalendarGate, clocks, tool_rows
from .parallel_tools_support import parallel_repo as source_repo_fixture
from .test_agent_runtime_pg import queued
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer, cycle, modify, prepare


@pytest.fixture(name="parallel_repo")
def repository_fixture(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


@pytest.mark.parametrize("stop", ["cancel", "withdraw"])
def test_late_actual_read_results_have_no_steps_aliases_next_model_or_final(
    parallel_repo: Any, monkeypatch: Any, stop: str
) -> None:
    repo, events = parallel_repo, []
    run = queued(repo)
    memory = MemoryService(repo)
    fact = memory.save_fact(
        "alice", "self", run["request"]["source_message_id"], run["request"]["message"], "preference"
    )
    gate, changed, errors = CalendarGate(repo, agent_tools_reads.almanac), [], []
    monkeypatch.setattr(agent_tools_reads, "almanac", gate)

    def stop_run() -> None:
        try:
            assert gate.started.wait(3)
            if stop == "cancel":
                modify(repo, run, "cancel_requested_at=now()")
            else:
                memory.retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
            changed.append(time.monotonic())
        except BaseException as error:
            errors.append(error)
            gate.release.set()

    stopper = threading.Thread(target=stop_run)
    stopper.start()
    port = ScriptedPort([answer("", clocks(17, 18)), answer("不可发布")])
    try:
        with pytest.raises(CoreError):
            AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
                SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], events.append
            )
        assert changed and time.monotonic() - changed[0] < 2
    finally:
        gate.close()
        stopper.join(timeout=2)
    assert not errors and not stopper.is_alive()
    assert len(port.requests) == 1 and repo.fetch_run("alice", run["id"])["result"] is None
    assert all(row["output"] is None and row["status"] != "completed" for row in tool_rows(repo, run))
    assert not [row for row in events if row["type"] in {"tool_result", "final"}]
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]


def test_partial_batch_crash_replays_only_unfinished_read_with_stable_operation(
    parallel_repo: Any, monkeypatch: Any
) -> None:
    repo = parallel_repo
    run, registry, frozen = prepare(repo)
    actual, observed = agent_tools_reads.almanac, []
    fail = [True]

    def compute(at: Any, zone: str) -> Any:
        observed.append(at.day)
        if at.day == 18 and fail[0]:
            raise SystemExit("synthetic read worker crash")
        return actual(at, zone)

    monkeypatch.setattr(agent_tools_reads, "almanac", compute)
    with pytest.raises(SystemExit):
        cycle(ScriptedPort([answer("", clocks(17, 18))]), registry, run, frozen).execute()
    before = tool_rows(repo, run)
    assert [row["status"] for row in before] == ["completed", "started"]
    fail[0] = False
    modify(repo, run, "lease_until=now()-interval '1 second'")
    reclaimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    port = ScriptedPort([answer("恢复完成")])
    outcome = cycle(port, registry, reclaimed, frozen).execute()
    after = tool_rows(repo, run)
    assert outcome.stop_reason == "completed" and len(port.requests) == 1
    assert observed.count(17) == 1 and observed.count(18) == 2
    assert [(row["seq"], row["input_fp"]) for row in after] == [(row["seq"], row["input_fp"]) for row in before]
    assert all(row["status"] == "completed" for row in after)

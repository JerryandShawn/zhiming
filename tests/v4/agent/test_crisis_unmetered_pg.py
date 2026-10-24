"""Unverified input counters block providers while preserving a real crisis reply."""

from types import SimpleNamespace

import pytest

from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.domain.contracts import CoreError

from .test_agent_runtime_pg import queued, repository_fixture
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter


@pytest.fixture(name="crisis_repo")
def repository(p2_repo, monkeypatch):
    yield from repository_fixture.__wrapped__(p2_repo, monkeypatch)


class UnverifiedMeter:
    version = "unverified_counter_v1"
    provider = "unverified"
    model = "unknown"
    live_admissible = False

    def measure(self, *args, **kwargs):
        raise InputMeterUnverified()


@pytest.mark.parametrize("message", ["我现在不想活了", "我已经准备伤害自己"])
def test_crisis_template_needs_no_admitted_model_request(crisis_repo, message):
    repo, events = crisis_repo, []
    run = queued(repo, message)
    port = ScriptedPort([])
    result = AgentRuntime(repo, port, UnverifiedMeter(), offline=True).execute(
        SimpleNamespace(repo=repo),
        "alice",
        run["id"],
        run["lease_token"],
        events.append,
    )
    assert result["text"] == "我这边暂时没法回答，稍后再试。"
    assert repo.fetch_run("alice", run["id"])["status"] == "succeeded"
    assert result["usage"]["model_steps"] == 0 and port.requests == []
    assert events[-1]["type"] == "final" and result["review"]["state"] == "skipped"


def test_noncrisis_does_not_bypass_meter_admission(crisis_repo):
    repo = crisis_repo
    run = queued(repo, "合成普通对话")
    port = ScriptedPort([])
    result = AgentRuntime(repo, port, UnverifiedMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assert result["text"] == "我这边暂时没法回答，稍后再试。" and port.requests == []


@pytest.mark.parametrize("meter", [None, SyntheticMeter()])
def test_crisis_cycle_admission_failure_also_commits_template(crisis_repo, meter):
    repo = crisis_repo
    run = queued(repo, "我现在不想活了")
    port = ScriptedPort([])
    result = AgentRuntime(repo, port, meter, offline=False).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assert result["usage"]["model_steps"] == 0
    assert result["text"] == "我这边暂时没法回答，稍后再试。" and port.requests == []


@pytest.mark.parametrize("stop", ["cancel", "withdraw"])
def test_template_never_bypasses_cancellation_or_source_withdrawal(crisis_repo, stop):
    repo = crisis_repo
    run = queued(repo, "我现在不想活了")

    class StoppingMeter(UnverifiedMeter):
        def measure(self, *args, **kwargs):
            if stop == "cancel":
                DispatcherCancellation(repo).request("alice", run["id"])
            else:
                with repo.transaction("alice") as connection:
                    repo.revoke(
                        connection,
                        "alice",
                        "message",
                        run["request"]["source_message_id"],
                        "delete",
                    )
            raise InputMeterUnverified()

    port = ScriptedPort([])
    with pytest.raises(CoreError):
        AgentRuntime(repo, port, StoppingMeter(), offline=True).execute(
            SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
        )
    assert port.requests == [] and repo.fetch_run("alice", run["id"])["status"] != "succeeded"
    assert not [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]

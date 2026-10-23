"""Merged or newly adopted crisis originals cannot hide behind a later ordinary message."""

from types import SimpleNamespace

import pytest

from mingjing_core.agent.context_types import InputMeterUnverified
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.port import ToolCall

from .test_agent_runtime_pg import repository_fixture
from .test_crisis_unmetered_pg import UnverifiedMeter
from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_turn_sources_runtime_pg import intake


@pytest.fixture(name="turn_crisis_repo")
def repository(p2_repo, monkeypatch):
    yield from repository_fixture.__wrapped__(p2_repo, monkeypatch)


def test_earlier_merged_crisis_source_still_gets_zero_model_template(turn_crisis_repo):
    repo = turn_crisis_repo
    ingress, thread = intake(repo)
    originals = [
        ingress.receive(owner="alice", thread_id=thread, message=text, request_id=str(index))
        for index, text in enumerate(("我现在不想活了", "然后想聊喝茶", "最后还有普通补充"))
    ]
    queued = ingress.queue(
        owner="alice", thread_id=thread, source_ids=[row["id"] for row in originals], request_id="crisis"
    )
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    port = ScriptedPort([])
    result = AgentRuntime(repo, port, UnverifiedMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assert all(number in result["text"] for number in ("12356", "120", "110"))
    assert port.requests == []
    assert {row["id"] for row in originals}.issubset(repo.get("alice", "message", result["message_id"])["source_ids"])


@pytest.mark.parametrize("failure", ["provider", "meter"])
def test_inflight_crisis_switches_next_request_to_text_only_and_keeps_fallback(turn_crisis_repo, failure):
    repo = turn_crisis_repo
    ingress, thread = intake(repo)
    queued = ingress.submit(owner="alice", thread_id=thread, message="合成普通问题", request_id="normal")
    run = repo.claim_run("alice", queued["id"], lease_seconds=150)
    child = []

    class CrisisPort(ScriptedPort):
        def stream(self, messages, **kwargs):
            if self.requests:
                assert kwargs["tools"] == []
                raise ModelUnavailable()
            child.append(
                ingress.submit(owner="alice", thread_id=thread, message="我现在不想活了", request_id="late-crisis")
            )
            yield from super().stream(messages, **kwargs)

    class CrisisMeter(SyntheticMeter):
        def measure(self, messages, tools, *, tool_choice):
            if failure == "meter" and any(message.content == "我现在不想活了" for message in messages):
                raise InputMeterUnverified()
            return super().measure(messages, tools, tool_choice=tool_choice)

    port = CrisisPort([answer("", [ToolCall("clock-before-crisis", "time_context", {})])])
    result = AgentRuntime(repo, port, CrisisMeter(), offline=True).execute(
        SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"]
    )
    assert "12356" in result["text"] and "120" in result["text"] and "110" in result["text"]
    assert child[0]["request"]["source_message_id"] in repo.get("alice", "message", result["message_id"])["source_ids"]
    assert repo.list("alice", "fact") == []

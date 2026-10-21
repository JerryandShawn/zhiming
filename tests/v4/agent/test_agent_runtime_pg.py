"""Injected scripted requests traverse real PG snapshots, journals and final commit."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.agent.events import validate_event
from mingjing_core.agent.loop_policy import RunControl
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.errors import ModelQuotaExhausted, ModelUnavailable
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import (
    ScriptedPort,
    SyntheticMeter,
    answer,
    modify,
    writer,
)
from .test_loop_cycle_support import cycle_repo as source_repo_fixture


@pytest.fixture(name="runtime_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)


def queued(repo: PostgresRepository, text: str = "我喜欢合成夜班") -> dict[str, Any]:
    source = MemoryService(repo).receive("alice", content=text, source_id=uuid.uuid4().hex, at=get_clock().now())
    run = repo.queue_run(
        "alice", uuid.uuid4().hex, {"message": text, "source_message_id": source["id"], "case_ids": []}
    )
    modify(repo, run, "runtime='v4',thread_id='life:self'")
    return repo.claim_run("alice", run["id"], lease_seconds=150)


def invoke(repo: PostgresRepository, run: dict, port: ScriptedPort, **options: Any) -> tuple[dict, list[dict]]:
    events: list[dict] = []
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True, **options)
    result = runtime.execute(SimpleNamespace(repo=repo), "alice", run["id"], run["lease_token"], events.append)
    return result, events


def test_life_runtime_commits_once_and_persists_each_original_meter(runtime_repo: PostgresRepository) -> None:
    repo, events = runtime_repo, []
    run = queued(repo)
    port = ScriptedPort([answer("", [ToolCall("write", "memory_write", writer(run))]), answer("已记住〔f1〕")])
    result, events = invoke(repo, run, port)
    assert result["schema"] == "core4.0" and result["text"] == "已记住〔f1〕"
    current = repo.fetch_run("alice", run["id"])
    assert current["status"] == "succeeded" and len(repo.list("alice", "fact")) == 1
    assert len(current["usage"]["context_sends"]) == 2
    assert len(current["usage"]["context_steps"]) == 2
    assert current["usage"]["agent_runtime"]["prompt_versions"]["system"]["version"] == "1.1.0"
    assert [row["data"]["seq"] for row in events] == list(range(1, len(events) + 1))
    assert events[-1]["type"] == "final"
    for event in events:
        validate_event(event["type"], event["data"])
    assert "合成受控推理" not in json.dumps(events, ensure_ascii=False)
    same, replay_events = invoke(repo, run, ScriptedPort([]))
    assert same == result and replay_events == []
    assistant = [row for row in repo.list("alice", "message") if row.get("role") == "assistant"]
    assert len(assistant) == 1


def test_critic_revise_generates_once_with_private_reasoning_preserved(runtime_repo: PostgresRepository) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    port = ScriptedPort([answer("你一定成功"), answer("这只是一个可能性")])
    critic = ScriptedPort(
        [
            answer(
                json.dumps(
                    {
                        "verdict": "revise",
                        "issues": [
                            {"type": "fatalism", "quote": "一定成功", "severity": 4, "fix_hint": "说明不确定性"}
                        ],
                    }
                )
            )
        ]
    )
    result, events = invoke(repo, run, port, critic=critic)
    assert result["review"]["state"] == "revised" and result["text"] == "这只是一个可能性"
    assert len(port.requests) == 2 and len(critic.requests) == 1
    assert all(not row.reasoning for row in critic.requests[0]["messages"])
    assert "合成受控推理" not in json.dumps([row.content for row in critic.requests[0]["messages"]], ensure_ascii=False)
    assert any(row.reasoning == "合成受控推理" for row in port.requests[1]["messages"])
    assert port.requests[1]["tools"] == []
    assert sum(row["type"] == "text_reset" and row["data"]["reason"] == "revised" for row in events) == 1


@pytest.mark.parametrize("failure", [ModelUnavailable(), ModelQuotaExhausted()])
def test_crisis_provider_failure_commits_audited_template(runtime_repo: PostgresRepository, failure: Exception) -> None:
    class FailedPort(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Any:
            raise failure

    repo, run = runtime_repo, queued(runtime_repo, "我现在不想活了")
    result, events = invoke(repo, run, FailedPort([]))
    assert all(number in result["text"] for number in ("12356", "120", "110"))
    assert result["review"]["state"] == "skipped" and events[-1]["type"] == "final"
    assert repo.fetch_run("alice", run["id"])["usage"]["agent_runtime"]["fallback"] == "crisis_template"


def test_incognito_is_explicitly_rejected_until_private_runtime_is_wired(runtime_repo: PostgresRepository) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    modify(repo, run, "thread_id='incognito:synthetic'")
    with pytest.raises(EvidenceError, match="无痕"):
        invoke(repo, run, ScriptedPort([]))


def test_ask_user_public_event_matches_committed_question(runtime_repo: PostgresRepository) -> None:
    repo, run = runtime_repo, queued(runtime_repo)
    question = {
        "question": "你更在意什么？",
        "options": ["时间", "收入"],
        "allow_free_text": True,
        "why": "答案影响建议",
        "slot": "最在意因素",
        "changes_conclusion": "影响建议顺序",
    }
    result, events = invoke(repo, run, ScriptedPort([answer("", [ToolCall("ask", "ask_user", question)])]))
    public = next(event["data"] for event in events if event["type"] == "ask_user")
    assert {key: public[key] for key in result["asked"]} == result["asked"]
    assert events[-1]["type"] == "final" and result["asked"]["question"] in result["text"]


def test_crisis_twenty_seconds_without_body_switches_to_program_template(runtime_repo: PostgresRepository) -> None:
    elapsed = [0.0]

    def controls(*args: Any, **kwargs: Any) -> RunControl:
        return RunControl(*args, **kwargs, monotonic=lambda: elapsed[0])

    class DelayedPort(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Any:
            from mingjing_core.models.port import StreamEvent

            elapsed[0] = 21
            yield StreamEvent("reasoning", "只在私有协议中使用的合成推理")

    repo, run = runtime_repo, queued(runtime_repo, "我想伤害自己")
    result, events = invoke(repo, run, DelayedPort([]), control_factory=controls)
    assert "12356" in result["text"] and "120" in result["text"] and "110" in result["text"]
    assert repo.fetch_run("alice", run["id"])["usage"]["agent_runtime"]["fallback_reason"] == "crisis_no_text"
    assert "只在私有协议" not in json.dumps(events, ensure_ascii=False)

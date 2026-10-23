"""Supplements enter the actual runtime loop and gain tool authority only after model proof."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer
from .test_thread_inbox_pg import ingress, repository_fixture, set_runtime, submit  # noqa: F401


def test_tool_boundary_supplement_is_modeled_written_and_committed_once(inbox_repo: PostgresRepository) -> None:
    repo = inbox_repo
    set_runtime(repo, "v4")
    service, thread = ingress(repo)
    parent = repo.claim_run("alice", submit(service, thread, "合成先了解当前时间")["id"])
    arguments = {"message_id": "pending", "quote": "我喜欢合成夜班", "kind": "preference", "summary": "合成普通偏好"}
    port = ScriptedPort(
        [
            answer("", [ToolCall("clock", "time_context", {})]),
            answer("", [ToolCall("remember", "memory_write", arguments)]),
            answer("合成已记住〔f1〕"),
        ]
    )
    received: list[dict[str, Any]] = []

    def observe(event: dict[str, Any]) -> None:
        if event["type"] == "tool_result" and event["data"]["name"] == "time_context":
            fallback = submit(service, thread, "我喜欢合成夜班")
            received.append(fallback)
            arguments["message_id"] = fallback["request"]["source_message_id"]

    result = AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        service.service, "alice", parent["id"], parent["lease_token"], observe
    )
    assert result["schema"] == "core4.0" and len(received) == 1 and len(port.requests) == 3
    facts = repo.list("alice", "fact")
    assert len(facts) == 1 and facts[0]["content"] == "我喜欢合成夜班"
    adopted = received[0]["request"]["source_message_id"]
    assert any(
        message.role == "user" and message.content == "我喜欢合成夜班" for message in port.requests[1]["messages"]
    )
    reply = repo.get("alice", "message", result["message_id"])
    assert adopted in reply["source_ids"]
    ThreadInbox(repo).recover("alice")
    assert repo.fetch_run("alice", received[0]["id"])["status"] == "cancelled"
    assert ThreadInbox(repo).recover("alice")["consumed"] == 0


def test_input_arriving_during_final_model_is_retained_for_next_turn(inbox_repo: PostgresRepository) -> None:
    repo = inbox_repo
    set_runtime(repo, "v4")
    service, thread = ingress(repo)
    parent = repo.claim_run("alice", submit(service, thread)["id"])
    received = []

    class DuringModel(ScriptedPort):
        def stream(self, messages: Any, **kwargs: Any) -> Any:
            received.append(submit(service, thread, "合成迟到补充"))
            yield from super().stream(messages, **kwargs)

    port = DuringModel([answer("合成第一轮回答")])
    AgentRuntime(repo, port, SyntheticMeter(), offline=True).execute(
        service.service, "alice", parent["id"], parent["lease_token"]
    )
    ThreadInbox(repo).recover("alice")
    assert len(port.requests) == 1 and repo.fetch_run("alice", received[0]["id"])["status"] == "queued"
    item = repo.get("alice", "request", "thread-inbox:" + received[0]["id"])
    assert item["inbox_state"] == "queued"

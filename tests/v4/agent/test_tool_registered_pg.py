"""A scripted ModelPort request traverses registered tools and real PG effects."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from mingjing_core.agent.journal import input_fingerprint
from mingjing_core.agent.toolkit import ToolContext
from mingjing_core.models.port import ChatMessage, ModelPort, StreamEvent, ToolCall, ToolSpec
from mingjing_core.repositories.postgres import PostgresRepository

from .test_tool_interactions_pg import QUESTION
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_tool_repo


@pytest.fixture
def tool_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_tool_repo.__wrapped__(p2_repo, monkeypatch)


class ScriptedToolPort(ModelPort):
    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name, self.arguments, self.calls = name, arguments, 0
        self.tool_names: list[str] = []

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.calls += 1
        tools: list[ToolSpec] = kwargs["tools"]
        self.tool_names = [tool.name for tool in tools]
        assert self.name in self.tool_names and messages[-1].role == "user"
        yield StreamEvent("tool_call", ToolCall("synthetic-call", self.name, self.arguments))
        yield StreamEvent("done", {"model": "scripted-tool-component"})


@pytest.mark.parametrize("name", ["ask_user", "set_reminder"])
def test_one_scripted_model_request_calls_registered_application_and_persists_real_effect(
    tool_repo: PostgresRepository,
    name: str,
) -> None:
    h = setup(tool_repo, "提醒我2026-10-21 20:00开会")
    args = (
        QUESTION
        if name == "ask_user"
        else {
            "text": "开会",
            "due_at": "2026-10-21T20:00:00+08:00",
            "message_id": h.source["id"],
            "quote": h.source["content"],
        }
    )
    model_step = h.journal.next_or_replay(h.run, kind="model", input_fp=input_fingerprint("model", "", {}))
    model_ctx = ToolContext.from_step(model_step, thread_id="life:self", source_ids=(h.source["id"],))
    port = ScriptedToolPort(name, args)
    response = port.complete([ChatMessage("user", h.source["content"])], tools=h.registry.specs(model_ctx))
    h.journal.complete(
        model_step,
        {
            "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in response.tool_calls
            ]
        },
    )
    call = response.tool_calls[0]
    versions = {"message:" + h.source["id"]: h.source["revision"]}
    tool_repo.set_run_dependencies("alice", h.run["id"], versions, h.run["lease_token"])
    step = h.journal.next_or_replay(
        h.run,
        kind="tool",
        name=call.name,
        input_fp=h.registry.fingerprint(call.name, call.arguments, source_versions=versions),
    )
    ctx = ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],), source_versions=versions)
    output = h.registry.execute(call.name, call.arguments, ctx)
    completed = h.journal.complete(step, output.model_dump())
    assert output.ok and completed.output["receipt"]["write_status"] == "saved"
    assert port.calls == 1 and 1 <= len(port.tool_names) <= 15
    assert "case_update" not in port.tool_names and "tarot_start" not in port.tool_names
    if name == "set_reminder":
        row = tool_repo.get("alice", "reminder", output.receipt["id"])
        assert row["due_at"] == "2026-10-21T12:00:00+00:00"
    else:
        assert (
            output.ends_turn and tool_repo.get("alice", "thread", "life:self")["clarify_slots"][0]["asked_count"] == 1
        )

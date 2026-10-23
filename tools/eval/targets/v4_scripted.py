"""Offline ModelPort adapter; scripts cannot supply DB state or receipts."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Iterator
from typing import Any

from mingjing_core.agent.context_budget import count_request
from mingjing_core.agent.context_tokens import TokenReading
from mingjing_core.models.errors import ModelProtocolError
from mingjing_core.models.port import ChatMessage, ModelPort, StreamEvent, ToolCall
from tools.eval.providers.scripted import ScriptedProvider


class ScriptedMeter:
    version = "synthetic_serialized_policy_units_only_v1"
    provider = "scripted"
    model = "scripted-v4"
    live_admissible = False

    def measure(self, messages: Any, tools: Any, *, tool_choice: str) -> TokenReading:
        size = count_request(messages, tools, tool_choice=tool_choice).serialized_bytes
        return TokenReading(None, size)


class ScriptedModelPort(ModelPort):
    """Only declared model output enters the real runtime; observed state cannot."""

    offline = True

    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.bindings: dict[str, str] = {}
        self.text_chunk_hook: Callable[[int], None] | None = None

    def start(self, provider: ScriptedProvider, turn: int, bindings: dict[str, str]) -> None:
        actions = provider.replay(turn)
        if any(not action or set(action) - {"text", "tool_call", "text_chunks"} for action in actions):
            raise ValueError("v4 scripts may contain model text/tool calls only")
        for action in actions:
            if "text_chunks" in action:
                chunks = action["text_chunks"]
                if (
                    set(action) != {"text", "text_chunks"}
                    or not isinstance(chunks, list)
                    or not 2 <= len(chunks) <= 64
                    or any(not isinstance(chunk, str) or not chunk for chunk in chunks)
                    or not isinstance(action["text"], str)
                    or len(action["text"]) > 200_000
                    or "".join(chunks) != action["text"]
                ):
                    raise ValueError("offline text chunks must exactly partition the same model text")
        self.actions, self.bindings = actions, dict(bindings)

    def _value(self, value: Any, messages: list[ChatMessage]) -> Any:
        if isinstance(value, list):
            return [self._value(item, messages) for item in value]
        if isinstance(value, dict):
            return {key: self._value(item, messages) for key, item in value.items()}
        if not isinstance(value, str):
            return value
        if value in self.bindings:
            return self.bindings[value]
        if value == "$unique_memory_fact":
            return unique_memory_fact(messages)
        if value.startswith("$last_receipt."):
            key = value.removeprefix("$last_receipt.")
            for message in reversed(messages):
                if message.role == "tool":
                    receipt = json.loads(message.content).get("receipt") or {}
                    if key in receipt:
                        return receipt[key]
            raise ModelProtocolError()
        if value == "$last_draw":
            for message in reversed(messages):
                if message.role == "tool":
                    draw = json.loads(message.content).get("data", {}).get("draw", {})
                    if draw.get("id"):
                        return draw["id"]
            raise ModelProtocolError()
        if value.startswith("$"):
            raise ModelProtocolError()
        return value

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.calls += 1
        self.requests.append(
            {"messages": copy.deepcopy(messages), "tool_names": [tool.name for tool in kwargs["tools"]]}
        )
        if not self.actions:
            raise ModelProtocolError()
        action = self.actions.pop(0)
        if "tool_call" in action:
            call = action["tool_call"]
            args = self._value(call.get("arguments", {}), messages)
            yield StreamEvent("tool_call", ToolCall(f"scripted-call-{self.calls}", call["name"], args))
        if "text" in action:
            for index, chunk in enumerate(action.get("text_chunks", [action["text"]]), 1):
                yield StreamEvent("text", chunk)
                if self.text_chunk_hook is not None:
                    self.text_chunk_hook(index)
        yield StreamEvent("usage", {})
        yield StreamEvent("done", {"model": "scripted-v4", "provider": "scripted"})


class ForbiddenLegacyModel:
    def generate(self, **kwargs: Any) -> dict[str, Any]:
        raise AssertionError("v4 evaluation cannot invoke a legacy or physical provider")


def unique_memory_fact(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role != "tool":
            continue
        calls = [
            call
            for prior in messages
            if prior.role == "assistant"
            for call in prior.tool_calls
            if call.id == message.tool_call_id and call.name == "memory_search"
        ]
        if not calls:
            continue
        result = json.loads(message.content)
        items = result.get("data", {}).get("items", [])
        if not result.get("ok") or len(items) != 1 or items[0].get("entity_kind") != "fact" or not items[0].get("id"):
            raise ModelProtocolError()
        return items[0]["id"]
    raise ModelProtocolError()

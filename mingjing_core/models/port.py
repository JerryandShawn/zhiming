"""Provider-neutral synchronous streaming contracts for executor threads."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from .errors import ModelUnavailable


@dataclass(frozen=True)
class Part:
    type: Literal["text", "image"] = "text"
    text: str = ""
    data: str = ""
    mime: str = "image/png"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[Part] = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    reasoning: str = field(default="", repr=False)
    reasoning_signature: str = field(default="", repr=False)
    tool_cycle: str | None = None
    private_content: list[dict[str, Any]] | None = field(default=None, repr=False)
    reasoning_present: bool = False


def active_tool_cycle(messages: list[ChatMessage]) -> str | None:
    """A new real user turn closes every earlier reasoning/tool cycle."""
    boundary = max((index for index, message in enumerate(messages) if message.role == "user"), default=-1)
    return next((message.tool_cycle for message in reversed(messages[boundary + 1 :]) if message.tool_cycle), None)


def reasoning_indices(messages: list[ChatMessage], caps: dict[str, Any]) -> set[int]:
    boundary = max((index for index, message in enumerate(messages) if message.role == "user"), default=-1)
    cycle = active_tool_cycle(messages)
    return {
        index
        for index, message in enumerate(messages)
        if caps.get("reasoning_replay")
        and cycle
        and index > boundary
        and message.role == "assistant"
        and message.tool_cycle == cycle
    }


@dataclass
class AssistantMessage:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str = field(default="", repr=False)
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    reasoning_signature: str = field(default="", repr=False)
    private_content: list[dict[str, Any]] | None = field(default=None, repr=False)
    reasoning_present: bool = False
    reasoning_signature_missing: int = 0
    execution_meta: dict[str, Any] = field(default_factory=dict)

    def as_chat(self, *, tool_cycle: str | None = None) -> ChatMessage:
        return ChatMessage(
            "assistant",
            self.text,
            self.tool_calls,
            reasoning=self.reasoning,
            reasoning_signature=self.reasoning_signature,
            tool_cycle=tool_cycle,
            private_content=deepcopy(self.private_content),
            reasoning_present=self.reasoning_present,
        )


@dataclass(frozen=True)
class StreamEvent:
    type: Literal["text", "tool_call", "reasoning", "usage", "done", "error"]
    data: Any = field(default=None, repr=False)


def with_execution_meta(events: Iterator[StreamEvent], metadata: dict[str, Any]) -> Iterator[StreamEvent]:
    for event in events:
        yield (
            StreamEvent("done", {**(event.data or {}), "execution_meta": dict(metadata)})
            if event.type == "done" and metadata
            else event
        )


class ModelPort:
    """Subclasses implement stream; complete raises typed stream failures."""

    def stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
        tool_choice: str = "auto",
        role: str = "primary",
        max_output: int | None = None,
        temperature: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[StreamEvent]:
        raise TypeError("ModelPort requires a concrete transport")

    def complete(self, messages: list[ChatMessage], **kwargs: Any) -> AssistantMessage:
        result = AssistantMessage()
        for event in self.stream(messages, **kwargs):
            if event.type == "text":
                result.text += event.data
            elif event.type == "reasoning":
                result.reasoning += event.data
                result.reasoning_present = True
            elif event.type == "tool_call":
                result.tool_calls.append(event.data)
            elif event.type == "usage":
                result.usage.update(event.data)
            elif event.type == "error":
                raise event.data if isinstance(event.data, ModelUnavailable) else ModelUnavailable()
            elif event.type == "done":
                for name in (
                    "model",
                    "provider",
                    "latency_ms",
                    "reasoning_signature",
                    "private_content",
                    "reasoning_signature_missing",
                    "execution_meta",
                ):
                    if name in (event.data or {}):
                        setattr(result, name, deepcopy(event.data[name]))
        return result

"""Provider-neutral synchronous streaming contracts for executor threads."""

from __future__ import annotations

import threading
from collections.abc import Iterator
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
    reasoning: str = ""
    reasoning_signature: str = ""
    tool_cycle: str | None = None


@dataclass
class AssistantMessage:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    reasoning_signature: str = ""

    def as_chat(self, *, tool_cycle: str | None = None) -> ChatMessage:
        return ChatMessage(
            "assistant",
            self.text,
            self.tool_calls,
            reasoning=self.reasoning,
            reasoning_signature=self.reasoning_signature,
            tool_cycle=tool_cycle,
        )


@dataclass(frozen=True)
class StreamEvent:
    type: Literal["text", "tool_call", "reasoning", "usage", "done", "error"]
    data: Any = None


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
            elif event.type == "tool_call":
                result.tool_calls.append(event.data)
            elif event.type == "usage":
                result.usage.update(event.data)
            elif event.type == "error":
                raise event.data if isinstance(event.data, ModelUnavailable) else ModelUnavailable()
            elif event.type == "done":
                for name in ("model", "provider", "latency_ms", "reasoning_signature"):
                    if name in (event.data or {}):
                        setattr(result, name, event.data[name])
        return result

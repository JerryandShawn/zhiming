"""OpenAI-compatible streaming wire adapter, independent of business policy."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

from .errors import CapabilityError, ModelProtocolError
from .port import ChatMessage, Part, StreamEvent, ToolCall, ToolSpec, active_tool_cycle
from .schema_flatten import flatten_schema
from .transport import StreamingHTTP, safe_usage, stream_error, strict_json


def _content(content: str | list[Part], vision: bool) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    result = []
    for part in content:
        if part.type == "image":
            if not vision:
                raise CapabilityError()
            result.append({"type": "image_url", "image_url": {"url": f"data:{part.mime};base64,{part.data}"}})
        else:
            result.append({"type": "text", "text": part.text})
    return result


def encode_messages(messages: list[ChatMessage], caps: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    # A caller tags the active tool cycle; reasoning from earlier user turns is excluded.
    active_cycle = active_tool_cycle(messages)
    for message in messages:
        row: dict[str, Any] = {"role": message.role, "content": _content(message.content, caps.get("vision", False))}
        if message.tool_calls:
            row["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False, allow_nan=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id:
            row["tool_call_id"] = message.tool_call_id
        field = caps.get("reasoning_field")
        if (
            active_cycle
            and field
            and caps.get("reasoning_replay")
            and message.reasoning
            and message.tool_cycle == active_cycle
        ):
            row[field] = message.reasoning
        result.append(row)
    return result


def _tool_calls(calls: dict[int, dict[str, str]]) -> Iterator[StreamEvent]:
    for _, call in sorted(calls.items()):
        failed = False
        try:
            arguments = strict_json(call["arguments"] or "{}")
            failed = not isinstance(arguments, dict) or not call["id"] or not call["name"]
        except (ValueError, TypeError):
            failed = True
        if failed:
            raise ModelProtocolError()
        yield StreamEvent("tool_call", ToolCall(call["id"], call["name"], arguments))


def parse_events(
    chunks: Iterator[dict[str, Any]], reasoning_field: str | None, *, membership: bool = False
) -> Iterator[StreamEvent]:
    calls: dict[int, dict[str, str]] = {}
    finished = False
    for chunk in chunks:
        if chunk.get("error"):
            raise stream_error(chunk["error"], membership=membership)
        if usage := safe_usage(chunk.get("usage")):
            yield StreamEvent("usage", usage)
        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})
            if delta.get("content"):
                yield StreamEvent("text", delta["content"])
            if reasoning_field and delta.get(reasoning_field):
                yield StreamEvent("reasoning", delta[reasoning_field])
            for item in delta.get("tool_calls", []):
                call = calls.setdefault(item.get("index", 0), {"id": "", "name": "", "arguments": ""})
                call["id"] += item.get("id", "")
                function = item.get("function", {})
                call["name"] += function.get("name", "")
                call["arguments"] += function.get("arguments", "")
            if choice.get("finish_reason"):
                if choice["finish_reason"] not in {"stop", "tool_calls", "function_call"}:
                    raise ModelProtocolError()
                finished = True
    if not finished:
        raise ModelProtocolError()
    yield from _tool_calls(calls)


class OpenAICompat(StreamingHTTP):
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
        body: dict[str, Any] = {
            "model": self.model,
            "messages": encode_messages(messages, self.caps),
            "stream": True,
            "max_tokens": max_output or self.settings.get("max_output", 14000),
        }
        if self.caps.get("include_usage"):
            body["stream_options"] = {"include_usage": True}
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            if not self.caps.get("tools", False):
                raise CapabilityError()
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters
                        if self.caps.get("probe_raw_schema")
                        else flatten_schema(tool.parameters, self.caps.get("schema_dialect", "openai")),
                    },
                }
                for tool in tools
            ]
            if tool_choice not in self.caps.get("tool_choice", ["auto"]):
                if tool_choice not in {tool.name for tool in tools} or "named" not in self.caps.get("tool_choice", []):
                    raise CapabilityError()
                body["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}
            else:
                body["tool_choice"] = tool_choice
        headers = {"Authorization": "Bearer " + self.api_key, "User-Agent": "MingjingCore/3.0"}
        yield from self._events(
            "/chat/completions",
            body,
            headers,
            lambda chunks: parse_events(chunks, self.caps.get("reasoning_field"), membership=self.membership),
            cancel_event,
        )

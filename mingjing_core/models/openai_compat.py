"""OpenAI-compatible streaming wire adapter, independent of business policy."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

from .errors import CapabilityError, ModelProtocolError, ModelResponseIdentityError
from .port import ChatMessage, Part, StreamEvent, ToolCall, ToolSpec, reasoning_indices, with_execution_meta
from .request_policy import safe_tool_choice
from .schema_flatten import flatten_schema
from .transport import StreamingHTTP, safe_usage, stream_error, strict_json
from .turn_coercion import replay_caps


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
    replay = reasoning_indices(messages, caps)
    for index, message in enumerate(messages):
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
        if index in replay and field and (message.reasoning or message.reasoning_present):
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
    chunks: Iterator[dict[str, Any]],
    reasoning_field: str | None,
    *,
    membership: bool = False,
    expected_model: str | None = None,
) -> Iterator[StreamEvent]:
    calls: dict[int, dict[str, str]] = {}
    finished = False
    identity_seen = False
    for chunk in chunks:
        if chunk.get("error"):
            raise stream_error(chunk["error"], membership=membership)
        if expected_model is not None:
            if (not identity_seen or "model" in chunk) and chunk.get("model") != expected_model:
                raise ModelResponseIdentityError()
            identity_seen = True
        if usage := safe_usage(chunk.get("usage")):
            yield StreamEvent("usage", usage)
        for choice in chunk.get("choices", []):
            delta = choice.get("delta", {})
            if delta.get("content"):
                yield StreamEvent("text", delta["content"])
            if reasoning_field and reasoning_field in delta and delta[reasoning_field] is not None:
                if not isinstance(delta[reasoning_field], str):
                    raise ModelProtocolError()
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
    if expected_model is not None and not identity_seen:
        raise ModelResponseIdentityError()
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
        tool_choice = safe_tool_choice(self.model, tools, tool_choice)
        metadata = self.execution_metadata(role)
        self.last_execution_meta = dict(metadata)
        caps = replay_caps(self.model, self.caps, self.settings, openai=True)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": encode_messages(messages, caps),
            "stream": True,
            "max_tokens": max_output or self.settings.get("max_output", 14000),
        }
        if self.model == "k3.1-pro":
            body["reasoning_effort"] = self.settings["reasoning_effort"]
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
        yield from with_execution_meta(
            self._events(
                "/chat/completions",
                body,
                headers,
                self._parsed_events,
                cancel_event,
            ),
            metadata,
        )

    def _parsed_events(self, chunks: Iterator[dict[str, Any]]) -> Iterator[StreamEvent]:
        caps = replay_caps(self.model, self.caps, self.settings, openai=True)
        yield from parse_events(
            chunks,
            caps.get("reasoning_field"),
            membership=self.membership,
            expected_model="k3.1-pro" if self.model == "k3.1-pro" else None,
        )

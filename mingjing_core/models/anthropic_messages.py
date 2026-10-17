"""Anthropic Messages SSE adapter retaining the v3 request protocol."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from .errors import (
    CapabilityError,
    ModelProtocolError,
)
from .port import ChatMessage, StreamEvent, ToolCall, ToolSpec, active_tool_cycle
from .schema_flatten import flatten_schema
from .transport import StreamingHTTP, safe_usage, stream_error, strict_json


def encode_messages(messages: list[ChatMessage], caps: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    system, result = [], []
    active = active_tool_cycle(messages)
    for message in messages:
        if message.role == "system":
            if not isinstance(message.content, str):
                raise CapabilityError()
            system.append(message.content)
            continue
        content: list[dict[str, Any]] = []
        if message.role == "tool":
            result_content = message.content if isinstance(message.content, str) else _parts(message.content, caps)
            content.append({"type": "tool_result", "tool_use_id": message.tool_call_id, "content": result_content})
        else:
            if isinstance(message.content, str):
                if message.content:
                    content.append({"type": "text", "text": message.content})
            else:
                content.extend(_parts(message.content, caps))
            if active and caps.get("reasoning_replay") and message.reasoning and message.tool_cycle == active:
                if not message.reasoning_signature:
                    raise CapabilityError()
                content.insert(
                    0, {"type": "thinking", "thinking": message.reasoning, "signature": message.reasoning_signature}
                )
            content.extend(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                for call in message.tool_calls
            )
        role = "user" if message.role == "tool" else message.role
        if result and result[-1]["role"] == role:
            result[-1]["content"].extend(content)
        else:
            result.append({"role": role, "content": content})
    return "\n\n".join(system), result


def _parts(parts: list[Any], caps: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for part in parts:
        if part.type == "image":
            if not caps.get("vision", False):
                raise CapabilityError()
            result.append({"type": "image", "source": {"type": "base64", "media_type": part.mime, "data": part.data}})
        else:
            result.append({"type": "text", "text": part.text})
    return result


def _call(block: dict[str, Any]) -> ToolCall:
    failed = False
    try:
        args = strict_json(block["partial"]) if block.get("partial") else block.get("input", {})
        failed = not isinstance(args, dict) or not block.get("id") or not block.get("name")
    except (ValueError, TypeError):
        failed = True
    if failed:
        raise ModelProtocolError()
    return ToolCall(block["id"], block["name"], args)


def parse_events(chunks: Iterator[dict[str, Any]], *, membership: bool = False) -> Iterator[StreamEvent]:
    blocks: dict[int, dict[str, Any]] = {}
    closed: set[int] = set()
    completed, signature = False, ""
    for chunk in chunks:
        kind = chunk.get("type")
        if kind == "error":
            raise stream_error(chunk.get("error", {}), membership=membership)
        if kind == "message_start":
            yield StreamEvent("usage", safe_usage(chunk.get("message", {}).get("usage")))
        elif kind == "content_block_start":
            blocks[chunk["index"]] = {**chunk["content_block"], "partial": ""}
            block = chunk["content_block"]
            if block.get("type") == "text" and block.get("text"):
                yield StreamEvent("text", block["text"])
        elif kind == "content_block_delta":
            delta = chunk["delta"]
            if delta.get("type") == "input_json_delta":
                blocks[chunk["index"]]["partial"] += delta.get("partial_json", "")
            elif delta.get("type") == "text_delta":
                yield StreamEvent("text", delta["text"])
            elif delta.get("type") == "thinking_delta":
                yield StreamEvent("reasoning", delta["thinking"])
            elif delta.get("type") == "signature_delta":
                signature += delta["signature"]
        elif kind == "content_block_stop":
            closed.add(chunk["index"])
        elif kind == "message_delta":
            if chunk.get("delta", {}).get("stop_reason") == "max_tokens":
                raise ModelProtocolError()
            yield StreamEvent("usage", safe_usage(chunk.get("usage")))
        elif kind == "message_stop":
            completed = True
    if not completed:
        raise ModelProtocolError()
    for index, block in sorted(blocks.items()):
        if block.get("type") == "tool_use":
            if index not in closed:
                raise ModelProtocolError()
            yield StreamEvent("tool_call", _call(block))
    if signature:
        yield StreamEvent("done", {"reasoning_signature": signature})


class AnthropicMessages(StreamingHTTP):
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
        system, encoded = encode_messages(messages, self.caps)
        body: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": encoded,
            "stream": True,
            "max_tokens": max_output or self.settings.get("max_output", 14000),
        }
        thinking = self.settings.get("thinking")
        if thinking:
            body["thinking"] = thinking
        temp = temperature if temperature is not None else self.settings.get("temperature")
        if temp is not None:
            body["temperature"] = temp
        if tools:
            if not self.caps.get("tools", False):
                raise CapabilityError()
            body["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters
                    if self.caps.get("probe_raw_schema")
                    else flatten_schema(tool.parameters, "anthropic"),
                }
                for tool in tools
            ]
            choices = self.caps.get("tool_choice", ["auto"])
            if tool_choice in {"auto", "none", "required"} and tool_choice in choices:
                body["tool_choice"] = {"type": "any" if tool_choice == "required" else tool_choice}
            elif "named" in choices and tool_choice in {tool.name for tool in tools}:
                body["tool_choice"] = {"type": "tool", "name": tool_choice}
            else:
                raise CapabilityError()
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "User-Agent": "MingjingCore/3.0"}
        yield from self._events(
            "/messages", body, headers, lambda chunks: parse_events(chunks, membership=self.membership), cancel_event
        )

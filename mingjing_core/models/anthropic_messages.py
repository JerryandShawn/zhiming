"""Anthropic Messages SSE adapter retaining the v3 request protocol."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

from .config_policy import ConfigError
from .errors import (
    CapabilityError,
    ModelProtocolError,
)
from .port import ChatMessage, StreamEvent, ToolCall, ToolSpec, reasoning_indices, with_execution_meta
from .request_policy import safe_tool_choice
from .schema_flatten import flatten_schema
from .transport import StreamingHTTP, safe_usage, stream_error, strict_json
from .turn_coercion import ContentBlocks, canonical_content, legacy_thinking, member_k3, replay_caps


def encode_messages(
    messages: list[ChatMessage], caps: dict[str, Any], *, allow_missing_signature: bool = False
) -> tuple[str, list[dict[str, Any]]]:
    system, result = [], []
    replay = reasoning_indices(messages, caps)
    for index, message in enumerate(messages):
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
            canonical = (
                canonical_content(message, replay=index in replay, allow_missing=allow_missing_signature)
                if message.role == "assistant"
                else None
            )
            if canonical is not None:
                content = canonical
            else:
                content.extend(legacy_thinking(message, replay=index in replay, allow_missing=allow_missing_signature))
                if isinstance(message.content, str):
                    if message.content:
                        content.append({"type": "text", "text": message.content})
                else:
                    content.extend(_parts(message.content, caps))
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
    blocks, completed = ContentBlocks(), False
    for chunk in chunks:
        kind = chunk.get("type")
        if completed and kind != "ping":
            raise ModelProtocolError()
        if kind == "error":
            raise stream_error(chunk.get("error", {}), membership=membership)
        if kind == "message_start":
            yield StreamEvent("usage", safe_usage(chunk.get("message", {}).get("usage")))
        elif kind in {"content_block_start", "content_block_delta"}:
            part = blocks.start(chunk) if kind == "content_block_start" else blocks.delta(chunk)
            if part and part[1]:
                yield StreamEvent(*part)
        elif kind == "content_block_stop":
            blocks.stop(chunk)
        elif kind == "message_delta":
            if chunk.get("delta", {}).get("stop_reason") == "max_tokens":
                raise ModelProtocolError()
            yield StreamEvent("usage", safe_usage(chunk.get("usage")))
        elif kind == "message_stop":
            completed = True
    if not completed:
        raise ModelProtocolError()
    content = blocks.complete(strict_json)
    for block in content:
        if block["type"] == "tool_use":
            yield StreamEvent("tool_call", _call(block))
    yield StreamEvent(
        "done",
        {
            "private_content": content,
            "reasoning_signature": "".join(
                block.get("signature", "") for block in content if block["type"] == "thinking"
            ),
            "reasoning_signature_missing": sum(
                block["type"] == "thinking" and not block.get("signature") for block in content
            ),
        },
    )


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
        if self.model == "k3.1-pro":
            raise ConfigError("首发K3.1 Pro仅使用已显式发送high且核响应身份的OpenAI原生协议")
        tool_choice = safe_tool_choice(self.model, tools, tool_choice)
        metadata = self.execution_metadata(role)
        caps = replay_caps(self.model, self.caps, self.settings)
        system, encoded = encode_messages(messages, caps, allow_missing_signature=member_k3(self.model, self.settings))
        if metadata:
            metadata["reasoning_replay_signature_missing"] = sum(
                block.get("type") == "thinking" and not block.get("signature")
                for row in encoded
                if row["role"] == "assistant"
                for block in row["content"]
            )
        self.last_execution_meta = dict(metadata)
        body: dict[str, Any] = {
            "model": self.model,
            "system": system,
            "messages": encoded,
            "stream": True,
            "max_tokens": max_output or self.settings.get("max_output", 14000),
        }
        thinking = self.settings.get("thinking")
        if thinking and not metadata:
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
        yield from with_execution_meta(
            self._events("/messages", body, headers, self._parsed_events, cancel_event), metadata
        )

    def _parsed_events(self, chunks: Iterator[dict[str, Any]]) -> Iterator[StreamEvent]:
        for event in parse_events(chunks, membership=self.membership):
            if event.type == "done":
                missing = event.data.get("reasoning_signature_missing", 0)
                self.reasoning_signature_missing = getattr(self, "reasoning_signature_missing", 0) + missing
            yield event

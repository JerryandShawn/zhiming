"""Private canonical assistant blocks and documented K3 turn policy."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from .config_policy import ConfigError, validate_model_settings
from .errors import CapabilityError, ModelProtocolError

if TYPE_CHECKING:
    from .port import ChatMessage

_BLOCKS = {"text", "thinking", "redacted_thinking", "tool_use"}
_ROLES = {"primary", "critic", "fast", "vision", "evaluation", "background"}


def member_k3(model: str, settings: Mapping[str, Any]) -> bool:
    return bool(settings.get("membership")) and model.strip().casefold().startswith("k3")


def turn_policy(model: str, settings: Mapping[str, Any], role: str) -> dict[str, Any]:
    validate_model_settings(model, settings)
    if not member_k3(model, settings):
        return {}
    if role not in _ROLES or settings.get("role_binding", role) != role:
        raise ConfigError("K3调用角色与已绑定角色不符")
    if any(settings.get(name) not in (None, "high") for name in ("effort", "reasoning_effort")):
        raise ConfigError("本阶段K3角色固定high，未经探针不得切换effort")
    # Kimi documents high by default; its Anthropic effort wire remains unprobed.
    # Send no guessed controls or the inherited 1024-token thinking budget.
    return {
        "role": role,
        "effort": "server_default/high",
        "effort_requested": "high",
        "effort_verified": False,
        "effort_source": "documented_default",
    }


def replay_caps(
    model: str, caps: Mapping[str, Any], settings: Mapping[str, Any], *, openai: bool = False
) -> dict[str, Any]:
    result = dict(caps)
    if member_k3(model, settings):
        result["reasoning_replay"] = True
        if openai:
            result["reasoning_field"] = "reasoning_content"
    return result


def _json(value: Any) -> str:
    result = None
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError):
        result = None
    if result is None:
        raise CapabilityError()
    return result


def _valid_block(block: Any) -> bool:
    if not isinstance(block, dict) or not isinstance(kind := block.get("type"), str) or kind not in _BLOCKS:
        return False
    if kind == "text":
        return isinstance(block.get("text"), str)
    if kind == "thinking":
        return isinstance(block.get("thinking"), str) and (
            "signature" not in block or isinstance(block["signature"], str)
        )
    if kind == "redacted_thinking":
        return isinstance(block.get("data"), str)
    return isinstance(block.get("input"), dict) and all(
        isinstance(block.get(key), str) and bool(block[key]) for key in ("id", "name")
    )


def canonical_content(message: ChatMessage, *, replay: bool, allow_missing: bool) -> list[dict[str, Any]] | None:
    if message.private_content is None:
        return None
    blocks = deepcopy(message.private_content)
    if not isinstance(blocks, list) or not all(_valid_block(block) for block in blocks):
        raise CapabilityError()
    _json(blocks)
    text = "".join(block.get("text", "") for block in blocks if block["type"] == "text")
    calls = [
        {"id": block.get("id"), "name": block.get("name"), "input": block.get("input")}
        for block in blocks
        if block["type"] == "tool_use"
    ]
    expected = [{"id": call.id, "name": call.name, "input": call.arguments} for call in message.tool_calls]
    if text != message.content or _json(calls) != _json(expected):
        raise CapabilityError()
    if replay:
        for block in blocks:
            if block["type"] == "thinking" and not block.get("signature") and not allow_missing:
                raise CapabilityError()
        return blocks
    return [block for block in blocks if block["type"] not in {"thinking", "redacted_thinking"}]


def legacy_thinking(message: ChatMessage, *, replay: bool, allow_missing: bool) -> list[dict[str, Any]]:
    if not replay or not (message.reasoning or message.reasoning_signature):
        return []
    block = {"type": "thinking", "thinking": message.reasoning}
    if message.reasoning_signature:
        block["signature"] = message.reasoning_signature
    elif not allow_missing:
        raise CapabilityError()
    return [block]


class ContentBlocks:
    """SSE block closure and boundaries are separate from legacy flat strings."""

    def __init__(self) -> None:
        self.blocks: dict[int, dict[str, Any]] = {}
        self.closed: set[int] = set()
        self.partial: dict[int, str] = {}

    def _index(self, chunk: dict[str, Any]) -> int:
        index = chunk.get("index")
        if type(index) is not int or index < 0:
            raise ModelProtocolError()
        return index

    def start(self, chunk: dict[str, Any]) -> tuple[str, str] | None:
        index, block = self._index(chunk), deepcopy(chunk.get("content_block"))
        if index in self.blocks or set(self.blocks) != self.closed or not _valid_block(block):
            raise ModelProtocolError()
        kind = block.get("type")
        self.blocks[index] = block
        if kind in {"text", "thinking"}:
            field = "text" if kind == "text" else "thinking"
            return ("text" if kind == "text" else "reasoning", block[field])
        return None

    def delta(self, chunk: dict[str, Any]) -> tuple[str, str] | None:
        index, delta = self._index(chunk), chunk.get("delta")
        if index not in self.blocks or index in self.closed or not isinstance(delta, dict):
            raise ModelProtocolError()
        fields = {
            "text_delta": ("text", "text"),
            "thinking_delta": ("thinking", "thinking"),
            "signature_delta": ("thinking", "signature"),
            "input_json_delta": ("tool_use", "partial_json"),
        }
        expected = fields.get(delta.get("type"))
        if expected is None:
            raise ModelProtocolError()
        kind, field = expected
        block, value = self.blocks[index], delta.get(field)
        if block["type"] != kind or not isinstance(value, str):
            raise ModelProtocolError()
        if field == "partial_json":
            if block["input"]:
                raise ModelProtocolError()
            self.partial[index] = self.partial.get(index, "") + value
        else:
            block[field] = block.get(field, "") + value
        return ("text" if field == "text" else "reasoning", value) if field in {"text", "thinking"} else None

    def stop(self, chunk: dict[str, Any]) -> None:
        index = self._index(chunk)
        if index not in self.blocks or index in self.closed:
            raise ModelProtocolError()
        self.closed.add(index)

    def complete(self, parse_json: Callable[[str], Any]) -> list[dict[str, Any]]:
        if set(self.blocks) != self.closed or sorted(self.blocks) != list(range(len(self.blocks))):
            raise ModelProtocolError()
        result = deepcopy([block for _, block in sorted(self.blocks.items())])
        for index, partial in self.partial.items():
            value = None
            try:
                value = parse_json(partial or "{}")
            except (ValueError, TypeError):
                value = None
            if not isinstance(value, dict):
                raise ModelProtocolError()
            result[index]["input"] = value
        return result

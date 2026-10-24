"""Limit the old single-submit API to fresh turns with the current K3 wire policy."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .config_policy import ConfigError
from .errors import ModelBadRequest
from .port import ToolSpec
from .quota_http import membership_endpoint
from .request_policy import safe_tool_choice, sampling_body
from .turn_coercion import turn_policy


class LegacyConversationUnsupported(ModelBadRequest):
    code = "LEGACY_CONVERSATION_UNSUPPORTED"


def configured_model(
    base: str, explicit: str | None, environment_model: str | None
) -> str:
    if explicit:
        return explicit
    previous = environment_model or "kimi-k3"
    if membership_endpoint(base) or previous.strip().casefold().startswith("k3"):
        return "k3-256k"
    return previous


def member_body(body: dict[str, Any], *, model: str, role: str) -> dict[str, Any]:
    if model not in {"k3", "k3-256k"} or body.get("model") != model:
        raise ConfigError("旧会员入口仅接受明确的K3模型身份")
    controls = {
        key: body[key]
        for key in ("thinking", "effort", "reasoning_effort")
        if key in body
    }
    turn_policy(model, {**controls, "membership": True, "role_binding": role}, role)
    _fresh_user(body.get("messages"))
    tools = body.get("tools", [])
    if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
        raise ModelBadRequest()
    specs = [
        ToolSpec(
            tool.get("name", ""),
            tool.get("description", ""),
            tool.get("input_schema", {}),
        )
        for tool in tools
    ]
    choice = body.get("tool_choice", {"type": "auto"})
    if not isinstance(choice, dict):
        raise ModelBadRequest()
    raw_choice = choice.get("type")
    if not isinstance(raw_choice, str):
        raise ModelBadRequest()
    selected = safe_tool_choice(
        model, specs, "required" if raw_choice == "any" else raw_choice
    )
    # The legacy submit API requires its single structured result; v4 loops do not.
    if len(specs) == 1:
        selected = "required"
    allowed = {
        "model",
        "system",
        "messages",
        "tools",
        "tool_choice",
        "max_tokens",
        "temperature",
        "top_p",
        "thinking",
        "effort",
        "reasoning_effort",
    }
    if set(body) - allowed:
        raise ModelBadRequest()
    result = sampling_body(deepcopy(body), {"sampling_fixed": True})
    for key in ("thinking", "effort", "reasoning_effort"):
        result.pop(key, None)
    if specs:
        result["tool_choice"] = {
            "type": "any" if selected == "required" else "auto",
            "disable_parallel_tool_use": True,
        }
    else:
        result.pop("tools", None)
        result.pop("tool_choice", None)
    return result


def _fresh_user(messages: Any) -> None:
    if not isinstance(messages, list) or len(messages) != 1:
        raise LegacyConversationUnsupported()
    message = messages[0]
    if (
        not isinstance(message, dict)
        or message.get("role") != "user"
        or set(message) != {"role", "content"}
    ):
        raise LegacyConversationUnsupported()
    content = message["content"]
    if isinstance(content, str):
        return
    if (
        not isinstance(content, list)
        or not content
        or any(
            not isinstance(part, dict) or part.get("type") not in {"text", "image"}
            for part in content
        )
    ):
        raise LegacyConversationUnsupported()

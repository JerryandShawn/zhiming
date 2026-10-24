"""Opt-in v3 generate shim; preserves one submit contract and legacy budgets."""

from __future__ import annotations

import json
from typing import Any

from .errors import ModelProtocolError
from .port import ChatMessage, Part, ToolSpec
from .registry import ModelRegistry


class PortBackedModel:
    def __init__(self, registry: ModelRegistry, *, role: str = "primary", stop_on_quota: bool = False) -> None:
        self.registry, self.role = registry, role
        self.port = registry.port(role, stop_on_quota=stop_on_quota)

    def generate(self, *, system: str, payload: dict[str, Any], schema: dict[str, Any], purpose: str) -> dict[str, Any]:
        handles = self.registry.resolve(self.role)
        choices = [handle.caps.get("tool_choice", ["auto"]) for handle in handles]
        forced = bool(choices) and all("named" in choice for choice in choices)
        reference = dict(payload)
        images = reference.pop("_image_inputs", [])
        parts = [Part(text=json.dumps(reference, ensure_ascii=False, allow_nan=False))]
        parts.extend(Part(type="image", data=image["data"], mime=image["mime"]) for image in images)
        if not forced:
            system += "\n请调用 submit，一次完整提交所有必填字段。"
        result = self.port.complete(
            [ChatMessage("system", system), ChatMessage("user", parts)],
            tools=[ToolSpec("submit", "提交本阶段完整结构化结果。", schema)],
            tool_choice="required" if purpose == "eval_critic" else "submit" if forced else "auto",
            role=self.role,
            max_output=14000 if purpose in {"synthesis", "review", "repair"} else 6000,
        )
        if len(result.tool_calls) != 1 or result.tool_calls[0].name != "submit":
            raise ModelProtocolError()
        usage = dict(result.usage)
        for original, target in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            if original in usage and target not in usage:
                usage[target] = usage[original]
        return {
            "output": result.tool_calls[0].arguments,
            "usage": usage,
            "latency_seconds": round(result.latency_ms / 1000, 3),
            "model": result.model,
            "provider": result.provider,
        }

"""Effort identity is a local policy claim, never a fabricated Kimi live result."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.registry import ModelRegistry

from .test_protocols import recording
from .test_u39_anthropic_wire import block_record, model_for

PROTOCOLS = [AnthropicMessages, OpenAICompat]


def data(protocol: type[Any]) -> bytes:
    return (
        block_record([])
        if protocol is AnthropicMessages
        else recording({"choices": [{"delta": {}, "finish_reason": "stop"}]})
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("role", ["primary", "critic", "fast", "vision", "evaluation", "background"])
def test_member_k3_uses_documented_default_without_guessing_wire_controls(protocol: type[Any], role: str) -> None:
    port, requests = model_for(
        protocol, content=data(protocol), settings={"thinking": {"type": "enabled", "budget_tokens": 1024}}
    )
    result = port.complete([], role=role)
    body = json.loads(requests[0].content)
    assert all(key not in body for key in ("thinking", "reasoning_effort", "effort", "output_config"))
    assert result.execution_meta["role"] == role
    assert result.execution_meta["effort"] == "server_default/high"
    assert result.execution_meta["effort_requested"] == "high"
    assert result.execution_meta["effort_verified"] is False
    assert result.execution_meta["effort_source"] == "documented_default"


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize(
    "changed",
    [
        {"effort": "low"},
        {"effort": "max"},
        {"reasoning_effort": "low"},
        {"reasoning_effort": "unknown"},
        {"role_binding": "critic"},
        {"thinking": False},
    ],
)
def test_mutated_adapter_settings_cannot_lower_effort_or_change_bound_role(
    protocol: type[Any], changed: dict[str, Any]
) -> None:
    port, requests = model_for(protocol, content=data(protocol))
    port.settings.update(changed)
    with pytest.raises(ConfigError):
        port.complete([], role="primary")
    assert requests == [] and port.request_count == 0


def test_non_k3_keeps_its_existing_thinking_wire_configuration() -> None:
    port, requests = model_for(model="portable", settings={"thinking": {"type": "enabled", "budget_tokens": 1024}})
    result = port.complete([])
    assert json.loads(requests[0].content)["thinking"]["budget_tokens"] == 1024
    assert result.execution_meta == {}


def registry_config(tmp_path: Path) -> ModelRegistry:
    value = {
        "version": 1,
        "providers": {
            "synthetic": {
                "protocol": "anthropic_messages",
                "api_key_env": "SYNTHETIC_KEY",
                "base_url": "https://synthetic.invalid/v1",
                "settings": {"membership": True},
            }
        },
        "models": {"k3": {"provider": "synthetic", "model": "k3", "settings": {}, "caps": {}}},
        "roles": {name: ["k3"] for name in ("primary", "critic", "fast")},
    }
    path = tmp_path / "u39-models.yaml"
    path.write_bytes(yaml.safe_dump(value).encode())
    return ModelRegistry(path, environment={"SYNTHETIC_KEY": "synthetic"})


def test_resolved_role_is_bound_without_mutating_shared_settings(tmp_path: Path) -> None:
    registry = registry_config(tmp_path)
    primary, critic, fast = (registry.resolve(role)[0] for role in ("primary", "critic", "fast"))
    assert (primary.role, critic.role, fast.role) == ("primary", "critic", "fast")
    primary.settings["role_binding"] = "fast"
    requests: list[httpx.Request] = []
    port = primary.adapter(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, content=block_record([]))
        )
    )
    with pytest.raises(ConfigError):
        port.complete([], role="fast")
    result = port.complete([], role="primary")
    assert result.execution_meta["role"] == "primary" and len(requests) == 1
    assert registry.resolve("critic")[0].settings == critic.settings


def test_bound_registry_port_rejects_role_override_before_factory(tmp_path: Path) -> None:
    calls: list[int] = []
    registry = registry_config(tmp_path)
    port = registry.port(role="primary", factory=lambda _: calls.append(1))
    with pytest.raises(ConfigError):
        port.complete([], role="critic")
    assert calls == []

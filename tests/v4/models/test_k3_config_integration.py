"""Registry and direct adapters enforce K3 policy before credential or HTTP use."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.registry import ModelRegistry
from mingjing_core.models.transport import StreamingHTTP

from .test_schema_registry import registry as fixture_registry


def _configuration(
    tmp_path: Path, *, model: str, thinking: Any, membership: bool = True, model_env: bool = False
) -> Path:
    original = fixture_registry(tmp_path)
    original.data["providers"]["one"]["settings"] = {"membership": membership}
    entry = original.data["models"]["a"]
    entry.update(model=model, settings={"thinking": thinking})
    if model_env:
        entry["model_env"] = "EFFECTIVE_MODEL"
    original.path.write_text(yaml.safe_dump(original.data), encoding="utf-8")
    return original.path


@pytest.mark.parametrize("thinking", [False, "off", {"type": "disabled"}, {"enabled": False}])
def test_declared_k3_is_rejected_even_without_credentials(tmp_path: Path, thinking: Any) -> None:
    path = _configuration(tmp_path, model="k3-256k", thinking=thinking)
    with pytest.raises(ConfigError, match="禁止关闭思考"):
        ModelRegistry(path, environment={})


def test_declared_k3_cannot_hide_behind_non_k3_environment_override(tmp_path: Path) -> None:
    path = _configuration(tmp_path, model="k3", thinking=False, model_env=True)
    with pytest.raises(ConfigError):
        ModelRegistry(path, environment={"EFFECTIVE_MODEL": "deepseek-chat"})


@pytest.mark.parametrize("effective", ["k3", "K3-256K"])
def test_effective_environment_k3_is_rejected_without_credentials(tmp_path: Path, effective: str) -> None:
    path = _configuration(tmp_path, model="non-k3-test-model", thinking=False, model_env=True)
    with pytest.raises(ConfigError):
        ModelRegistry(path, environment={"EFFECTIVE_MODEL": effective})


def test_resolve_rechecks_caller_mutated_registry_settings(tmp_path: Path) -> None:
    path = _configuration(tmp_path, model="k3-256k", thinking=None)
    registry = ModelRegistry(path, environment={"KEY1": "synthetic-key"})
    assert registry.resolve()[0].model == "k3-256k"
    registry.data["models"]["a"]["settings"]["thinking"] = {"type": "disabled"}
    registry.environment = {}
    with pytest.raises(ConfigError):
        registry.resolve()


def test_resolve_rechecks_effective_model_after_environment_changes(tmp_path: Path) -> None:
    path = _configuration(tmp_path, model="non-k3-test-model", thinking=False, model_env=True)
    environment = {"KEY1": "synthetic-key", "EFFECTIVE_MODEL": "deepseek-chat"}
    registry = ModelRegistry(path, environment=environment)
    assert registry.resolve()[0].model == "deepseek-chat"
    environment["EFFECTIVE_MODEL"] = "k3-256k"
    with pytest.raises(ConfigError):
        registry.resolve()


def test_caller_mutated_resolved_handle_is_rejected_before_http(tmp_path: Path) -> None:
    path = _configuration(tmp_path, model="k3-256k", thinking=None)
    handle = ModelRegistry(path, environment={"KEY1": "synthetic-key"}).resolve()[0]
    handle.settings["thinking"] = False
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200))
    with pytest.raises(ConfigError):
        handle.adapter(transport=transport)
    assert requests == []


@pytest.mark.parametrize("adapter", [AnthropicMessages, OpenAICompat])
def test_direct_adapter_construction_rejects_thinking_off_with_zero_http(adapter: type[StreamingHTTP]) -> None:
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200))
    with pytest.raises(ConfigError):
        adapter(
            base_url="https://synthetic.invalid/v1",
            api_key="",
            model="k3-256k",
            provider="synthetic",
            settings={"membership": True, "thinking": {"type": "disabled"}},
            transport=transport,
        )
    assert requests == []


@pytest.mark.parametrize(
    "model,thinking,membership", [("k3", False, False), ("deepseek-chat", False, True), ("k3-256k", None, True)]
)
def test_legal_registry_and_adapter_configurations_keep_existing_contract(
    tmp_path: Path, model: str, thinking: Any, membership: bool
) -> None:
    path = _configuration(tmp_path, model=model, thinking=thinking, membership=membership)
    handle = ModelRegistry(path, environment={"KEY1": "synthetic-key"}).resolve()[0]
    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200))
    instance = handle.adapter(transport=transport)
    assert instance.model == model
    assert instance.membership is membership
    assert requests == []

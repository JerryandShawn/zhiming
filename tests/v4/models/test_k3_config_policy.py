"""Pure preflight model-identity checks; no credentials, PG or HTTP are needed."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any

import pytest

from mingjing_core.models.config_policy import ConfigError, validate_model_settings


@pytest.mark.parametrize("model", ["k3", "k3-256k", "K3", " K3-256K "])
@pytest.mark.parametrize(
    "thinking",
    [
        False,
        0,
        "disabled",
        "OFF",
        " false ",
        {"type": "disabled"},
        {"type": "Off"},
        {"type": False},
        {"enabled": False},
        {"enabled": "no"},
        {"type": "enabled", "enabled": False},
    ],
)
def test_membership_k3_rejects_explicit_thinking_off(model: str, thinking: Any) -> None:
    settings = {"membership": True, "thinking": thinking}
    before = deepcopy(settings)
    with pytest.raises(ConfigError, match="禁止关闭思考"):
        validate_model_settings(model, settings)
    assert settings == before


@pytest.mark.parametrize(
    "settings",
    [
        {},
        {"thinking": None},
        {"thinking": True},
        {"thinking": {}},
        {"thinking": {"type": None}},
        {"thinking": {"enabled": None}},
        {"thinking": {"type": "enabled", "budget_tokens": 0}},
        {"thinking": {"type": "enabled", "budget_tokens": 1024}},
        {"thinking": {"type": "adaptive"}},
        {"reasoning_effort": None},
        {"reasoning_effort": "low"},
        {"effort": "high"},
        {"effort": "unknown-unvalidated-effort"},
    ],
)
def test_unspecified_or_enabled_thinking_keeps_server_default(settings: dict[str, Any]) -> None:
    merged = {"membership": True, **settings}
    before = deepcopy(merged)
    assert validate_model_settings("k3-256k", merged) is None
    assert merged == before


@pytest.mark.parametrize("field", ["reasoning_effort", "effort"])
def test_documented_none_effort_cannot_disable_k3_thinking(field: str) -> None:
    with pytest.raises(ConfigError):
        validate_model_settings("k3-256k", {"membership": True, field: " NoNe "})


@pytest.mark.parametrize("membership", [False, None, 0, ""])
def test_nonmembership_preserves_existing_configuration_contract(membership: Any) -> None:
    assert validate_model_settings("k3", {"membership": membership, "thinking": False}) is None


@pytest.mark.parametrize("model", ["deepseek-chat", "qwen-plus", "kimi-k3", "kimi-for-coding", ""])
def test_non_k3_models_preserve_existing_configuration_contract(model: str) -> None:
    assert validate_model_settings(model, {"membership": True, "thinking": False}) is None


def test_membership_check_matches_existing_transport_truthiness() -> None:
    # Transport treats a nonempty value as membership, even a quoted YAML value.
    with pytest.raises(ConfigError):
        validate_model_settings("k3", {"membership": "false", "thinking": False})


def test_effective_model_argument_is_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = {"membership": True, "thinking": False}
    monkeypatch.setenv("KIMI_MODEL", "deepseek-chat")
    with pytest.raises(ConfigError):
        validate_model_settings("K3-256K", settings)
    monkeypatch.setenv("KIMI_MODEL", "k3")
    assert validate_model_settings("deepseek-chat", settings) is None


def test_read_only_nested_mappings_and_private_values_are_safe() -> None:
    thinking = MappingProxyType({"type": "disabled", "private": "SYNTHETIC_PRIVATE_CONFIG"})
    settings = MappingProxyType({"membership": True, "thinking": thinking})
    with pytest.raises(ConfigError) as caught:
        validate_model_settings("k3", settings)
    assert caught.value.code == "MODEL_CONFIG_ERROR"
    assert isinstance(caught.value, ValueError)
    assert "SYNTHETIC_PRIVATE_CONFIG" not in repr(caught.value)
    assert caught.value.__cause__ is None

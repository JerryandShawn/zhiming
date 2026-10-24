"""D2 routing cannot silently follow the historical user's KIMI_MODEL=k3."""

from __future__ import annotations

from pathlib import Path

import pytest

from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.registry import ModelRegistry
from tools.probe_models import _handles


def registry() -> ModelRegistry:
    root = Path(__file__).resolve().parents[3]
    return ModelRegistry(
        root / "config/models.yaml",
        environment={
            "KIMI_API_KEY": "synthetic",
            "KIMI_MODEL": "k3",
            "DEEPSEEK_API_KEY": "synthetic-other",
        },
    )


@pytest.mark.parametrize("role", ["primary", "critic", "evaluation", "background", "fast", "vision"])
def test_every_active_role_uses_membership_k3_256k_with_high_effort(role: str) -> None:
    handles = registry().resolve(role)
    assert len(handles) == 1 and handles[0].model == "k3-256k"
    assert handles[0].settings["effort"] == "high"
    assert handles[0].settings["model_lock"] == "k3-256k"
    assert handles[0].caps["reasoning_replay"] and handles[0].caps["sampling_fixed"]
    assert not {"none", "named"} & set(handles[0].caps["tool_choice"])


def test_reintroduced_model_env_cannot_silently_downgrade_default() -> None:
    reg = registry()
    reg.data["models"]["kimi-code-main"]["model_env"] = "KIMI_MODEL"
    with pytest.raises(ConfigError, match="模型身份"):
        reg.resolve("primary")


def test_explicit_probe_clone_keeps_u39_and_uses_trusted_evaluation_role() -> None:
    reg = registry()
    handles = _handles(reg)
    assert [item.model for item in handles] == ["k3", "k3-256k"]
    assert all(item.role == "evaluation" and item.settings["effort"] == "high" for item in handles)
    assert all(item.caps["reasoning_replay"] and item.caps["sampling_fixed"] for item in handles)
    assert reg.resolve()[0].model == "k3-256k"

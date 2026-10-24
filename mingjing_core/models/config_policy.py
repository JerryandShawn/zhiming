"""Reject explicit thinking-off settings that would change membership K3 routing."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_DISABLED_WORDS = frozenset({"disabled", "disable", "false", "off", "no", "0", "none"})


class ConfigError(ValueError):
    """A model configuration violates a project model-identity requirement."""

    code = "MODEL_CONFIG_ERROR"


def _explicitly_disabled(value: object) -> bool:
    if value is False:
        return True
    if isinstance(value, str):
        return value.strip().casefold() in _DISABLED_WORDS
    return type(value) in (int, float) and value == 0


def validate_model_settings(model: str, settings: Mapping[str, Any]) -> None:
    """Validate an already resolved model/settings pair without I/O or mutation.

    Membership uses the existing transport's truthiness. Callers must pass the
    effective model after environment overrides and the merged provider settings.
    Missing/None thinking values retain the server default; this narrow policy
    does not validate token budgets, unknown effort values or provider schemas.
    """
    locked = settings.get("model_lock")
    if locked is not None and (not isinstance(locked, str) or model != locked):
        raise ConfigError("模型身份已锁定，不能由环境或调用参数切换")
    if model == "k3.1-pro" and any(settings.get(field) != "high" for field in ("effort", "reasoning_effort")):
        raise ConfigError("首发K3.1 Pro必须显式配置high，不能沿用默认max或关闭思考")
    if not settings.get("membership", False) or not model.strip().casefold().startswith("k3"):
        return
    thinking = settings.get("thinking")
    disabled = _explicitly_disabled(thinking)
    if isinstance(thinking, Mapping):
        disabled = any(_explicitly_disabled(thinking.get(field)) for field in ("type", "enabled"))
    # Kimi's documented effort mapping explicitly turns `none` into thinking off:
    # https://www.kimi.com/code/docs/kimi-code/models.html
    effort_off = any(
        isinstance(value := settings.get(field), str) and value.strip().casefold() == "none"
        for field in ("reasoning_effort", "effort")
    )
    if disabled or effort_off:
        raise ConfigError("Kimi Code 会员端点的 K3 模型禁止关闭思考；请移除关闭配置或启用思考，以免切换模型。")

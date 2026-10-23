"""Repository-owned loop limits; callers cannot provide a file path or raise caps."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    model_validator,
)

from mingjing_core.domain.contracts import EvidenceError

from .loop_policy import LoopPolicy

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config/runtime.yaml"
CAPS = {"interactive": (40, 480, 6), "background": (60, 1200, 10)}


class RuntimeConfigError(EvidenceError):
    code = "RUNTIME_CONFIG_INVALID"


class LaneLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    max_iterations: StrictInt = Field(gt=0)
    max_seconds: StrictInt = Field(gt=0)
    max_tools: StrictInt = Field(gt=0)
    repeat_limit: StrictInt = Field(gt=0, le=3)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: StrictInt = Field(ge=1, le=1)
    interactive: LaneLimits
    background: LaneLimits
    lease_seconds: StrictInt = Field(gt=0, le=150)
    renew_seconds: StrictInt = Field(gt=0, le=20)

    @model_validator(mode="after")
    def approved_limits(self) -> Self:
        for lane, caps in CAPS.items():
            values = getattr(self, lane)
            for name, cap in zip(("max_iterations", "max_seconds", "max_tools"), caps, strict=True):
                if getattr(values, name) > cap:
                    raise ValueError("运行配置不能扩大通道上限")
        if self.renew_seconds >= self.lease_seconds:
            raise ValueError("续租间隔必须小于租约")
        return self

    @property
    def sha256(self) -> str:
        return config_hash(self.model_dump())

    def policy(self, lane: str, depth: str, *, crisis: bool = False) -> LoopPolicy:
        if lane not in CAPS or depth not in {"standard", "deep"}:
            raise RuntimeConfigError("运行配置的通道或深度无效")
        limits = getattr(self, lane)
        return LoopPolicy(
            depth=depth,
            lane=lane,
            **limits.model_dump(),
            lease_seconds=self.lease_seconds,
            renew_seconds=self.renew_seconds,
            text_only=crisis,
        )


def config_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_runtime_config(value: Any) -> RuntimeConfig:
    if type(value) is RuntimeConfig:
        value = value.model_dump()
    try:
        return RuntimeConfig.model_validate(value, strict=True)
    except (ValidationError, TypeError, ValueError):
        raise RuntimeConfigError("运行安全配置不符合批准的结构或上限") from None


class UniqueKeyLoader(yaml.SafeLoader):
    """Even trusted files must not silently override a duplicated safety key."""


def unique_mapping(loader: UniqueKeyLoader, node: Any) -> dict[str, Any]:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise RuntimeConfigError("运行安全配置有重复或无效字段")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_runtime_config() -> RuntimeConfig:
    try:
        if CONFIG_PATH.is_symlink() or CONFIG_PATH.resolve() != CONFIG_PATH.absolute():
            raise RuntimeConfigError("运行安全配置位置无效")
        raw = CONFIG_PATH.read_bytes()
        if len(raw) > 16_384:
            raise RuntimeConfigError("运行安全配置过大")
        value = yaml.load(raw.decode("utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError):
        raise RuntimeConfigError("运行安全配置缺失或无法读取") from None
    return validate_runtime_config(value)

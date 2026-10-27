"""Trusted batch 3 release switches read from one checked-in YAML file."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError

from mingjing_core.agent.runtime_config import UniqueKeyLoader
from mingjing_core.domain.contracts import EvidenceError

SWITCHES_PATH = Path(__file__).resolve().parents[2] / "config" / "switches.yaml"
ReviewMode = Literal["risk", "always", "off"]


class ReleaseSwitches(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: StrictInt = Field(ge=1, le=1)
    streaming_v2: StrictBool
    review_mode: ReviewMode
    proactive: StrictBool


def validate_switches(value: Any) -> ReleaseSwitches:
    try:
        return ReleaseSwitches.model_validate(value)
    except ValidationError:
        raise EvidenceError("发布开关配置无效") from None


def load_switches(path: Path = SWITCHES_PATH) -> ReleaseSwitches:
    try:
        if path.is_symlink():
            raise EvidenceError("发布开关配置位置无效")
        raw = path.read_bytes()
        if len(raw) > 4096:
            raise EvidenceError("发布开关配置过大")
        value = yaml.load(raw.decode("utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError):
        raise EvidenceError("发布开关配置缺失或无法读取") from None
    return validate_switches(value)

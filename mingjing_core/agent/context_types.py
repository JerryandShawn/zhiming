"""Explicitly offline context contracts keep estimates separate from usage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mingjing_core.models.port import ChatMessage, ToolSpec


class ContextInputError(ValueError):
    """A context cannot safely be assembled from the supported inputs."""

    def __init__(self, code: str = "context_input_invalid") -> None:
        self.code = code
        super().__init__("上下文资料不完整或超出当前安全支持范围。")


class RequiredContextOverflow(ContextInputError):
    def __init__(self) -> None:
        super().__init__("context_required_overflow")


class InputMeterUnverified(ContextInputError):
    def __init__(self) -> None:
        super().__init__("provider_input_meter_unverified")


@dataclass(frozen=True)
class BudgetPolicy:
    target: int = 30_000
    compress_above: int = 120_000
    hard_max: int = 180_000
    large_tool: int = 8_000
    history_limit: int = 81
    fact_limit: int = 256
    revocation_limit: int = 512
    search_limit: int = 10
    source_ref_limit: int = 512

    def __post_init__(self) -> None:
        if any(type(value) is not int or value < 1 for value in vars(self).values()):
            raise ContextInputError("context_policy_invalid")
        if not self.target <= self.compress_above <= self.hard_max:
            raise ContextInputError("context_policy_invalid")
        if self.history_limit > 1000 or self.search_limit > 100 or self.fact_limit > 10_000:
            raise ContextInputError("context_policy_invalid")


@dataclass(frozen=True)
class ContextItem:
    key: str
    messages: tuple[ChatMessage, ...]
    required: bool = False
    summary: str | None = None
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContextLayer:
    name: str
    items: tuple[ContextItem, ...]


@dataclass(frozen=True)
class MeterResult:
    policy_units: int
    serialized_bytes: int
    meter_version: str = "policy_utf8_bytes_v1"
    unit: str = "policy_units"
    estimated_input_tokens: None = None
    input_token_upper_bound: None = None
    actual_input_tokens: None = None
    live_admissible: bool = False


@dataclass(frozen=True)
class BudgetResult:
    layers: tuple[ContextLayer, ...]
    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolSpec, ...]
    meter: MeterResult
    compression_trace: tuple[dict[str, str | int], ...]


@dataclass(frozen=True)
class SourceSnapshot:
    owner: str
    subject: str
    revision: int
    settings: dict[str, Any]
    facts: tuple[dict[str, Any], ...]
    history: tuple[dict[str, Any], ...]
    retrieved: tuple[dict[str, Any], ...]
    current: dict[str, Any]
    versions: dict[str, int]
    read_counts: dict[str, int]


@dataclass(frozen=True)
class ContextBuild:
    budget: BudgetResult
    snapshot_revision: int
    alias_map: dict[str, dict[str, str | int]]
    injected_versions: dict[str, int]
    read_counts: dict[str, int]
    limitations: tuple[str, ...] = field(
        default=("offline_policy_units", "runtime_unconnected", "provider_framing_unverified")
    )

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        return self.budget.messages

    @property
    def meter(self) -> MeterResult:
        return self.budget.meter

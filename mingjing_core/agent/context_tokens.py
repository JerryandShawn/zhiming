"""D2 token thresholds behind an injected meter; no guessed provider framing."""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Protocol

from mingjing_core.models.port import ChatMessage, ToolSpec

from .context_budget import (
    _flatten,
    _remove_candidate,
    _summarize_candidate,
    count_request,
)
from .context_types import (
    BudgetPolicy,
    BudgetResult,
    ContextInputError,
    ContextLayer,
    InputMeterUnverified,
    MeterResult,
    RequiredContextOverflow,
)


@dataclass(frozen=True)
class TokenReading:
    estimated: int | None
    upper_bound: int | None
    actual: int | None = None

    def validate(self) -> None:
        values = (self.estimated, self.upper_bound, self.actual)
        if any(value is not None and (type(value) is not int or value < 0) for value in values):
            raise ContextInputError("context_token_meter_invalid")
        if self.upper_bound is None:
            raise InputMeterUnverified()
        # Z1 treats actual > estimate upper as an observed calibration breach,
        # not corrupt provider usage. The three quantities remain independent.
        if self.estimated is not None and self.estimated > self.upper_bound:
            raise ContextInputError("context_token_meter_invalid")


class TokenMeter(Protocol):
    """Trusted application dependency, never an option controlled by model output.

    Implementations must cover tools, tool_choice and reasoning. Z1 permits a
    documented estimate with framing allowance; it does not certify equivalence.
    Synthetic meters are usable for threshold tests, with live_admissible=False.
    """

    version: str
    provider: str
    model: str
    live_admissible: bool

    def measure(
        self,
        messages: tuple[ChatMessage, ...],
        tools: tuple[ToolSpec, ...],
        *,
        tool_choice: str,
    ) -> TokenReading: ...


def measure_request(
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolSpec, ...],
    meter: TokenMeter,
    *,
    tool_choice: str,
) -> MeterResult:
    base = count_request(messages, tools, tool_choice=tool_choice)
    if any(not isinstance(value, str) or not value.strip() for value in (meter.version, meter.provider, meter.model)):
        raise InputMeterUnverified()
    reading = meter.measure(copy.deepcopy(messages), copy.deepcopy(tools), tool_choice=tool_choice)
    if not isinstance(reading, TokenReading):
        raise ContextInputError("context_token_meter_invalid")
    reading.validate()
    return replace(
        base,
        estimated_input_tokens=reading.estimated,
        input_token_upper_bound=reading.upper_bound,
        actual_input_tokens=reading.actual,
        live_admissible=meter.live_admissible is True,
        token_meter_version=meter.version,
        provider=meter.provider,
        model=meter.model,
        tokenizer_version=getattr(meter, "tokenizer_version", None),
        tokenizer_sha256=getattr(meter, "tokenizer_sha256", None),
        encoder_version=getattr(meter, "encoder_version", None),
        encoder_sha256=getattr(meter, "encoder_sha256", None),
        estimate_multiplier=getattr(meter, "estimate_multiplier", None),
        framing_allowance=getattr(meter, "framing_allowance", None),
    )


def apply_token_budget(
    layers: tuple[ContextLayer, ...],
    tools: tuple[ToolSpec, ...],
    *,
    meter: TokenMeter,
    policy: BudgetPolicy,
    tool_choice: str = "auto",
) -> BudgetResult:
    """Above 120k compress toward 30k; required material must fit below 180k."""
    layers, tools = copy.deepcopy(layers), copy.deepcopy(tools)
    measured = measure_request(_flatten(layers), tools, meter, tool_choice=tool_choice)
    trace: list[dict[str, str | int]] = []
    compress = measured.input_token_upper_bound > policy.compress_above
    for _ in range(sum(len(layer.items) for layer in layers)):
        if not compress or measured.input_token_upper_bound <= policy.target:
            break
        candidate = _remove_candidate(layers) or _summarize_candidate(layers, policy)
        if candidate is None:
            break
        changed, action = candidate
        after = measure_request(_flatten(changed), tools, meter, tool_choice=tool_choice)
        if after.input_token_upper_bound >= measured.input_token_upper_bound:
            raise ContextInputError("context_compression_not_reducing")
        trace.append(
            {
                "action": action,
                "before": measured.input_token_upper_bound,
                "after": after.input_token_upper_bound,
                "unit": "input_token_upper_bound",
            }
        )
        layers, measured = changed, after
    if measured.input_token_upper_bound > policy.hard_max:
        raise RequiredContextOverflow()
    return BudgetResult(layers, _flatten(layers), tools, measured, tuple(trace))

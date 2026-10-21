"""Synthetic token accounting proves D2 boundaries, never claims provider calibration."""

from __future__ import annotations

from dataclasses import replace

import pytest

from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_tokens import (
    TokenReading,
    apply_token_budget,
    measure_request,
)
from mingjing_core.agent.context_types import (
    BudgetPolicy,
    ContextInputError,
    ContextItem,
    ContextLayer,
    InputMeterUnverified,
    RequiredContextOverflow,
)
from mingjing_core.models.port import ChatMessage, ToolSpec


class SyntheticMeter:
    version = "synthetic_character_units_for_threshold_tests_only"
    provider = "scripted"
    model = "synthetic"
    live_admissible = False

    def measure(self, messages, tools, *, tool_choice):
        # Explicit synthetic unit, deliberately different from UTF-8 bytes.
        size = sum(
            len(message.content) + len(message.reasoning) + len(message.reasoning_signature) for message in messages
        ) + sum(len(tool.description) for tool in tools)
        return TokenReading(size - 1 if size else 0, size)


def layer(name: str, size: int, *, required: bool = False) -> ContextLayer:
    return ContextLayer(name, (ContextItem(name, (ChatMessage("system", "中" * size),), required),))


@pytest.mark.parametrize("upper", [0, 29_999, 30_000, 30_001, 60_000, 120_000, 120_001, 180_000])
def test_required_accepted_through_hard_boundary_without_truncating(upper: int) -> None:
    result = apply_token_budget(
        (layer("L0", upper, required=True),),
        (),
        meter=SyntheticMeter(),
        policy=BudgetPolicy(),
    )
    assert result.meter.input_token_upper_bound == upper
    assert result.meter.actual_input_tokens is None
    assert result.meter.serialized_bytes > upper
    assert result.messages[0].content == "中" * upper
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(result)


@pytest.mark.parametrize("upper", [180_001, 200_000])
def test_required_above_hard_limit_fails_closed(upper: int) -> None:
    with pytest.raises(RequiredContextOverflow):
        apply_token_budget(
            (layer("L0", upper, required=True),),
            (),
            meter=SyntheticMeter(),
            policy=BudgetPolicy(),
        )


def test_crossing_120k_compresses_history_then_retrieval_toward_target() -> None:
    layers = (
        layer("L0", 28_000, required=True),
        layer("L5", 80_000),
        layer("L4", 15_000),
    )
    result = apply_token_budget(layers, (), meter=SyntheticMeter(), policy=BudgetPolicy())
    assert result.meter.input_token_upper_bound == 28_000
    assert [row["action"] for row in result.compression_trace] == ["L5_drop", "L4_drop"]
    assert all(row["unit"] == "input_token_upper_bound" for row in result.compression_trace)
    assert len(layers[1].items) == 1  # No mutation of the frozen source context.


def test_soft_target_does_not_churn_a_120k_window() -> None:
    result = apply_token_budget((layer("L5", 120_000),), (), meter=SyntheticMeter(), policy=BudgetPolicy())
    assert not result.compression_trace and result.messages[0].content == "中" * 120_000


def test_configuration_cannot_raise_the_absolute_hard_limit() -> None:
    with pytest.raises(ContextInputError):
        BudgetPolicy(hard_max=180_001)


@pytest.mark.parametrize(
    "reading",
    [
        TokenReading(3, None),
        TokenReading(True, 4),
        TokenReading(5, 4),
        TokenReading(-1, 3),
    ],
)
def test_unknown_or_inconsistent_meter_never_passes(reading: TokenReading) -> None:
    class BadMeter(SyntheticMeter):
        def measure(self, *args, **kwargs):
            return reading

    with pytest.raises(ContextInputError):
        measure_request((ChatMessage("user", "合成"),), (), BadMeter(), tool_choice="auto")


def test_z1_observed_usage_above_estimate_is_preserved_for_calibration() -> None:
    class BreachedMeter(SyntheticMeter):
        def measure(self, *args, **kwargs):
            return TokenReading(2, 4, 5)

    result = measure_request((ChatMessage("user", "合成"),), (), BreachedMeter(), tool_choice="auto")
    assert (result.estimated_input_tokens, result.input_token_upper_bound, result.actual_input_tokens) == (2, 4, 5)


def test_all_request_fields_reach_injected_meter_separately_from_serialized_size() -> None:
    class CapturingMeter(SyntheticMeter):
        def measure(self, messages, tools, *, tool_choice):
            assert messages[0].reasoning == "受控推理" and messages[0].reasoning_signature == "签名"
            assert tools[0].name == "time_context" and tool_choice == "required"
            return TokenReading(120, 150, 137)

    message = replace(
        ChatMessage("assistant", "合成"),
        reasoning="受控推理",
        reasoning_signature="签名",
    )
    result = measure_request(
        (message,),
        (ToolSpec("time_context", "描述", {}),),
        CapturingMeter(),
        tool_choice="required",
    )
    assert (
        result.estimated_input_tokens,
        result.input_token_upper_bound,
        result.actual_input_tokens,
    ) == (120, 150, 137)
    assert result.policy_units == result.serialized_bytes and result.serialized_bytes != 150

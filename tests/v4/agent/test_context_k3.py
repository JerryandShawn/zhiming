"""Z1 uses explicit synthetic token IDs; no test claims a real K3 vocabulary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_k3 import K3EstimatedMeter, PinnedK3Counter, calibration
from mingjing_core.agent.context_tokens import apply_token_budget, measure_request
from mingjing_core.agent.context_types import (
    BudgetPolicy,
    ContextInputError,
    ContextItem,
    ContextLayer,
    InputMeterUnverified,
    MeterResult,
    RequiredContextOverflow,
)
from mingjing_core.models.port import ChatMessage, ToolSpec


class FixedCounter:
    version = "synthetic-k3-fixture-v1"
    artifact_sha256 = "a" * 64
    encoder_version = "synthetic-encoder-fixture-v1"
    encoder_sha256 = "b" * 64
    live_admissible = False

    def __init__(self, count: int) -> None:
        self.tokens, self.payload = count, ""

    def count(self, text: str) -> int:
        self.payload = text
        return self.tokens


@pytest.mark.parametrize("estimate,upper", [(0, 4000), (1, 4002), (20_000, 27_000), (153_043, 180_000)])
def test_public_count_formula_and_framing_allowance_are_labelled(estimate: int, upper: int) -> None:
    meter = K3EstimatedMeter(FixedCounter(estimate))
    result = measure_request((ChatMessage("user", "合成"),), (), meter, tool_choice="auto")
    assert result.estimated_input_tokens == estimate and result.input_token_upper_bound == upper
    assert result.actual_input_tokens is None and result.serialized_bytes != upper
    assert result.tokenizer_sha256 == "a" * 64 and result.encoder_sha256 == "b" * 64
    assert result.estimate_multiplier == "1.15" and result.framing_allowance == 4_000
    assert not result.live_admissible


def test_all_normalized_request_fields_reach_real_counter_seam() -> None:
    counter = FixedCounter(20)
    message = replace(ChatMessage("assistant", "合成"), reasoning="受控推理", reasoning_signature="签名")
    measure_request(
        (message,),
        (ToolSpec("time_context", "描述", {"type": "object"}),),
        K3EstimatedMeter(counter),
        tool_choice="required",
    )
    value = json.loads(counter.payload)
    assert value["messages"][0]["reasoning"] == "受控推理"
    assert value["messages"][0]["reasoning_signature"] == "签名"
    assert value["tools"][0]["parameters"] == {"type": "object"} and value["tool_choice"] == "required"


def test_180k_gate_applies_to_estimate_upper_not_strings() -> None:
    layers = (ContextLayer("L0", (ContextItem("system", (ChatMessage("system", "短"),), True),)),)
    result = apply_token_budget(layers, (), meter=K3EstimatedMeter(FixedCounter(153_043)), policy=BudgetPolicy())
    assert result.meter.input_token_upper_bound == 180_000
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(result)
    with pytest.raises(RequiredContextOverflow):
        apply_token_budget(layers, (), meter=K3EstimatedMeter(FixedCounter(153_044)), policy=BudgetPolicy())


@pytest.mark.parametrize("factor", ["1", "NaN", "Infinity", "-1", "not-a-number"])
def test_invalid_or_reduced_factor_is_rejected(factor: str) -> None:
    with pytest.raises(ContextInputError):
        K3EstimatedMeter(FixedCounter(5), factor=factor)


def test_unconfigured_counter_cannot_enable_a_live_request() -> None:
    with pytest.raises(InputMeterUnverified):
        K3EstimatedMeter(None)


def test_local_artifacts_are_hash_pinned_and_encoder_counts_ids(tmp_path: Path) -> None:
    vocabulary, encoder = tmp_path / "vocabulary.json", tmp_path / "encoder.py"
    vocabulary.write_text("synthetic vocabulary only")
    encoder.write_text("synthetic encoder only")
    counter = PinnedK3Counter(
        vocabulary,
        "fixture-v1",
        hashlib.sha256(vocabulary.read_bytes()).hexdigest(),
        encoder,
        "fixture-v1",
        hashlib.sha256(encoder.read_bytes()).hexdigest(),
        lambda text: [7, 11],
    )
    assert counter.count("字符串长度不是词元计量") == 2 and not counter.live_admissible
    with pytest.raises(InputMeterUnverified):
        replace(counter, artifact_sha256="0" * 64)
    with pytest.raises(ContextInputError):
        replace(counter, encode=lambda text: [True]).count("合成")


def test_breach_warns_and_adjusts_without_overwriting_any_measurement() -> None:
    meter = replace(
        MeterResult(100, 100),
        estimated_input_tokens=10_000,
        input_token_upper_bound=15_500,
        estimate_multiplier="1.15",
        tokenizer_sha256="a" * 64,
    )
    result = calibration({}, meter, 20_000)
    assert result["upper_bound_breached"] and Decimal(result["factor"]) == Decimal("2.2")
    assert meter.estimated_input_tokens == 10_000 and meter.input_token_upper_bound == 15_500
    assert calibration(result, meter, None)["factor"] == "2.2"
    assert calibration(result, replace(meter, tokenizer_sha256="b" * 64), None)["factor"] == "1.15"


def test_zero_estimate_is_an_alarm_with_no_invented_division_result() -> None:
    meter = replace(MeterResult(10, 10), estimated_input_tokens=0, input_token_upper_bound=4000)
    result = calibration({}, meter, 4001)
    assert result["upper_bound_breached"] and result["calibration_unavailable"]
    assert result["factor"] == "1.15"

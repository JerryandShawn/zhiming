"""Provider-usage substitutes calibrate once through real completed PG steps."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.agent.context_types import MeterResult
from mingjing_core.application.context_usage import ContextUsageService
from mingjing_core.application.memory import MemoryService
from mingjing_core.repositories.postgres import PostgresRepository

from .test_context_k3 import FixedCounter
from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive
from .test_context_usage_pg import completed


def test_breach_factor_and_metadata_survive_reopen_and_step_replay(p2_repo: PostgresRepository) -> None:
    meter = replace(
        MeterResult(100, 100),
        estimated_input_tokens=65_000,
        input_token_upper_bound=78_750,
        token_meter_version="public_k3_estimate_v1",
        tokenizer_version="synthetic-fixture",
        tokenizer_sha256="a" * 64,
        encoder_version="synthetic-fixture",
        encoder_sha256="b" * 64,
        estimate_multiplier="1.15",
        framing_allowance=4000,
        provider="scripted",
        model="k3-256k",
    )
    step = completed(p2_repo, "calibrate", {"input_tokens": 90_000})
    service = ContextUsageService(p2_repo)
    receipt = service.record(step, meter)
    assert receipt["actual_input_tokens"] == 90_000
    assert receipt["estimated_input_tokens"] == 65_000 and receipt["input_token_upper_bound"] == 78_750
    assert receipt["warnings"] == ["input_token_upper_bound_exceeded"]
    expected = Decimal(90_000) / Decimal(65_000) * Decimal("1.1")
    assert Decimal(receipt["calibration"]["factor"]) == expected
    assert service.record(step, meter) == receipt
    reopened = PostgresRepository(p2_repo.dsn, schema=p2_repo.schema, initialize=False)
    try:
        assert Decimal(ContextUsageService(reopened).factor("alice", "self", "life:self", meter)) == expected
        changed = replace(meter, tokenizer_sha256="c" * 64)
        assert ContextUsageService(reopened).factor("alice", "self", "life:self", changed) == "1.15"
    finally:
        reopened.close()


def test_context_estimate_is_explicitly_labelled_and_not_enabled_by_synthetic_counter(memory: MemoryService) -> None:
    source = receive(memory, "合成输入")
    context = ContextEngine(memory, "合成系统", token_meter=K3EstimatedMeter(FixedCounter(100))).build(
        "alice", source["id"]
    )
    assert "estimated_input_bound" in context.limitations and "provider_framing_unverified" in context.limitations
    assert not context.meter.live_admissible and context.meter.actual_input_tokens is None

"""A deliberately oversized PG history compresses under explicit synthetic accounting."""

from __future__ import annotations

import pytest

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_types import InputMeterUnverified, RequiredContextOverflow
from mingjing_core.application.memory import MemoryService

from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive, text_of
from .test_context_stress_pg import digest
from .test_context_tokens import SyntheticMeter


def test_large_history_compresses_without_touching_pg_and_keeps_far_constraints(memory: MemoryService) -> None:
    source = receive(memory, "请记住，我不能上夜班", "constraint")
    fact = memory.save_fact("alice", "self", source["id"], "我不能上夜班", "constraint")
    removed = receive(memory, "合成长历史" * 30_000, "huge-old")
    current = receive(memory, "目前如何安排", "current")
    before = digest(memory)
    engine = ContextEngine(memory, "合成系统", token_meter=SyntheticMeter())
    result = engine.build("alice", current["id"], query="目前")
    assert digest(memory) == before
    assert result.meter.input_token_upper_bound <= 30_000 and result.meter.actual_input_tokens is None
    assert "我不能上夜班" in text_of(result) and current["content"] == result.messages[-1].content
    assert result.injected_versions["fact:" + fact["id"]] == fact["revision"]
    assert "message:" + removed["id"] not in result.injected_versions
    assert any(row["before"] > 120_000 for row in result.budget.compression_trace)
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(result.budget)


def test_single_required_current_message_above_hard_limit_is_rejected_whole(memory: MemoryService) -> None:
    current = receive(memory, "合成正文。" * 36_200)
    before = digest(memory)
    with pytest.raises(RequiredContextOverflow):
        ContextEngine(memory, "合成系统", token_meter=SyntheticMeter()).build("alice", current["id"])
    assert digest(memory) == before

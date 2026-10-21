"""Synthetic long threads stay complete in PostgreSQL while requests stay bounded."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_types import InputMeterUnverified, RequiredContextOverflow
from mingjing_core.models.port import ModelPort, StreamEvent
from mingjing_core.timekit.clock import get_clock

from .test_context_pg import context_memory_fixture as context_memory_fixture
from .test_context_pg import receive, text_of

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mingjing_core.application.memory import MemoryService
    from mingjing_core.models.port import ChatMessage


CONSTRAINTS = ("我不能上夜班", "我对花生过敏", "我周末不参加活动")


class RecordingScriptedPort(ModelPort):
    def __init__(self) -> None:
        self.calls = 0
        self.last_messages: list[ChatMessage] = []

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.calls += 1
        self.last_messages = messages
        yield StreamEvent("text", "合成组件测试确认")
        yield StreamEvent("done", {"model": "scripted-context"})


def save_constraints(memory: MemoryService, source: dict[str, Any]) -> None:
    for quote in CONSTRAINTS:
        receipt = memory.save_fact("alice", "self", source["id"], quote, "constraint")
        assert receipt["write_status"] == "saved"


def digest(memory: MemoryService) -> tuple[int, str]:
    with memory.repo.transaction("alice") as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT id,data->>'content' AS content FROM {} WHERE owner=%s AND kind='message' ORDER BY id"
            ).format(memory.repo.table("core_entities")),
            ("alice",),
        ).fetchall()
    raw = json.dumps([(row["id"], row["content"]) for row in rows], ensure_ascii=False).encode("utf-8")
    return len(rows), hashlib.sha256(raw).hexdigest()


def evidence(name: str, value: dict[str, Any]) -> None:
    configured = os.getenv("P3_CONTEXT_EVIDENCE")
    if configured:
        directory = Path(configured)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", "utf-8")


def test_r07_three_hundred_rounds_keep_far_constraints_and_original_messages(memory: MemoryService) -> None:
    started = time.monotonic()
    engine = ContextEngine(memory, "合成系统：只能使用有效来源。", clock=get_clock())
    port = RecordingScriptedPort()
    maximum, counts = 0, {}
    for index in range(300):
        text = "请记住，" + "；".join(CONSTRAINTS) if index == 0 else f"合成轮次{index}现在该如何安排"
        source = receive(memory, text, str(index))
        if index == 0:
            save_constraints(memory, source)
        result = engine.build("alice", source["id"])
        assert all(quote in text_of(result) for quote in CONSTRAINTS)
        assert result.meter.policy_units <= 180_000
        assert result.read_counts["history_candidates"] <= 81
        maximum = max(maximum, result.meter.policy_units)
        counts = result.read_counts
        reply = port.complete(list(result.messages))
        memory.record_assistant_message(
            "alice", "self", "life:self", reply.text, run_id="stress:" + str(index), channel="web"
        )
        get_clock().advance(timedelta(minutes=1))
    before = digest(memory)
    final = engine.build("alice", source["id"])
    assert digest(memory) == before and before[0] == 600
    assert port.calls == 300
    evidence(
        "r07-300-rounds",
        {
            "rounds": 300,
            "messages": before[0],
            "source_sha256": before[1],
            "scripted_calls": port.calls,
            "provider_calls": 0,
            "unit": final.meter.unit,
            "maximum_policy_units": maximum,
            "candidate_counts": counts,
            "duration_seconds": time.monotonic() - started,
        },
    )


def seed_chunk(memory: MemoryService, start: int, end: int) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    with memory.repo.transaction("alice"):
        for index in range(start, end):
            if index % 2:
                text = "请记住，" + "；".join(CONSTRAINTS) if index == 1 else f"合成消息{index} 中文🙂 é"
                latest = receive(memory, text, str(index))
                if index == 1:
                    save_constraints(memory, latest)
            else:
                memory.record_assistant_message(
                    "alice", "self", "life:self", f"合成回复{index}", run_id="long:" + str(index), channel="web"
                )
            get_clock().advance(timedelta(seconds=1))
    return latest


def test_ten_thousand_messages_bound_pg_candidates_and_compress_without_changing_history(
    memory: MemoryService,
) -> None:
    started = time.monotonic()
    engine = ContextEngine(memory, "合成系统：保留关键约束。", clock=get_clock())
    measurements = []
    for start in range(0, 10_000, 100):
        source = seed_chunk(memory, start, start + 100)
        if start in (0, 900, 4900, 9900):
            result = engine.build("alice", source["id"])
            assert all(quote in text_of(result) for quote in CONSTRAINTS)
            assert result.read_counts["history_candidates"] <= 81
            assert result.read_counts["fact_catalog"] == 3
            assert result.meter.policy_units <= 180_000
            measurements.append({"messages": start + 100, "counts": result.read_counts})
    before = digest(memory)
    # This is real PG history, not a prebuilt layer injected into the ContextEngine.
    receive(memory, "h" * 125_000, "large-history")
    current = receive(memory, "压缩后仍完整保留当前问题和关键约束", "after-large")
    before_compress = digest(memory)
    result = engine.build("alice", current["id"])
    assert result.budget.compression_trace[0]["before"] > 120_000
    assert result.meter.policy_units <= 180_000
    assert all(quote in text_of(result) for quote in CONSTRAINTS)
    assert digest(memory) == before_compress
    huge = receive(memory, "x" * 181_000, "required-overflow")
    try:
        engine.build("alice", huge["id"])
    except RequiredContextOverflow:
        overflow_rejected = True
    else:
        raise AssertionError("required context was silently truncated")
    try:
        assert_live_allowed(result.budget)
    except InputMeterUnverified:
        live_blocked = True
    else:
        raise AssertionError("unknown membership framing was permitted")
    assert before[0] == 10_000
    evidence(
        "10000-messages",
        {
            "messages_before_extra_probes": before[0],
            "source_sha256": before[1],
            "original_messages_unchanged": True,
            "provider_calls": 0,
            "unit": result.meter.unit,
            "actual_input_tokens": None,
            "input_token_upper_bound": None,
            "checkpoints": measurements,
            "compression_trace": result.budget.compression_trace,
            "overflow_rejected": overflow_rejected,
            "unknown_framing_live_blocked": live_blocked,
            "duration_seconds": time.monotonic() - started,
        },
    )

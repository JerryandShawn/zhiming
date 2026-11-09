"""Real memory, followup and RuntimePort boundaries use U4 without external requests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from psycopg import sql

from mingjing_core.application.time_range_parser import ModuleTimeRangeParser
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, set_clock

from .test_agent_runtime_pg import invoke, queued
from .test_loop_cycle_support import ScriptedPort, answer, writer
from .test_loop_cycle_support import cycle_repo as source_fixture
from .test_tool_interactions_pg import call, schedule_args
from .test_toolkit_pg import SAID_AT, setup


@pytest.fixture
def repo(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> Iterator[PostgresRepository]:
    for repository in source_fixture.__wrapped__(p2_repo, monkeypatch):
        set_clock(FrozenClock(SAID_AT))
        yield repository


def test_memory_uses_original_said_at_preserves_quote_and_replays_once(
    repo: PostgresRepository,
) -> None:
    h = setup(repo, "我下周三参加面试，请记住", parser=ModuleTimeRangeParser())
    h.service.clock = FrozenClock(datetime.fromisoformat("2026-10-20T10:30:00+08:00"))
    result, context, arguments = h.write(kind="event")
    assert result.ok
    fact = repo.get("alice", "fact", result.receipt["id"])
    assert fact["event_at"] == "2026-10-21" and fact["original_expression"] == "下周三"
    assert (
        fact["said_at"] == "2026-10-17T02:30:00+00:00"
        and fact["owner_timezone"] == "Asia/Shanghai"
    )
    assert fact["content"] == h.source["content"] == fact["source_refs"][0]["quote"]
    revision = repo.get_revision("alice")
    assert (
        h.registry.execute("memory_write", arguments, context).receipt == result.receipt
    )
    assert (
        repo.get_revision("alice") == revision and len(repo.list("alice", "fact")) == 1
    )


@pytest.mark.parametrize(
    "text", ["我明天或后天参加面试", "我每周三面试"]
)
def test_uncertain_or_repeating_time_never_writes_a_single_event(
    repo: PostgresRepository, text: str
) -> None:
    h = setup(repo, text, parser=ModuleTimeRangeParser())
    result, _, _ = h.write(kind="event")
    assert result.receipt["write_status"] == "needs_confirmation"
    assert (
        result.receipt["code"] == "date_ambiguous" and repo.list("alice", "fact") == []
    )



def test_month_end_is_stored_as_a_range_without_inventing_an_occurrence_day(repo: PostgresRepository) -> None:
    # Document 41 permits range events; the old contract still forbids a made-up single date.
    h = setup(repo, "我月底参加面试", parser=ModuleTimeRangeParser())
    result, _, _ = h.write(kind="event")
    assert result.receipt["write_status"] == "saved"
    fact = repo.get("alice", "fact", result.receipt["id"])
    assert fact["precision"] == "range"
    assert fact["event_at"] == "2026-10-20T16:00:00+00:00"
    assert fact["event_end"] == "2026-10-31T16:00:00+00:00"
    assert fact["original_expression"] == "月底"
    assert fact["content"] == "我月底参加面试"
    assert fact["owner_timezone"] == "Asia/Shanghai"

def test_model_claimed_date_cannot_replace_module_date(
    repo: PostgresRepository,
) -> None:
    h = setup(repo, "我下周三参加面试", parser=ModuleTimeRangeParser())
    result, _, _ = h.write(kind="event", event_at="2026-10-28")
    assert (
        result.receipt["code"] == "date_conflict" and repo.list("alice", "fact") == []
    )


def test_revoked_original_interval_cannot_reuse_a_successful_receipt(
    repo: PostgresRepository,
) -> None:
    h = setup(repo, "我下周三参加面试", parser=ModuleTimeRangeParser())
    result, context, arguments = h.write(kind="event")
    assert result.ok
    with repo.transaction("alice") as connection:
        repo.revoke(
            connection,
            "alice",
            "source_span",
            "u4-withdrawn-original",
            "stopped",
            {"message_id": h.source["id"], "start": 0, "end": len(h.source["content"])},
        )
    revision = repo.get_revision("alice")
    assert not h.registry.execute("memory_write", arguments, context).ok
    assert (
        repo.get_revision("alice") == revision and len(repo.list("alice", "fact")) == 1
    )


def test_followup_uses_the_same_parser_without_producing_delivery(
    repo: PostgresRepository,
) -> None:
    h = setup(repo, "我下周三参加面试", parser=ModuleTimeRangeParser())
    result, _ = call(h, "schedule_followup", schedule_args(h))
    assert result.ok
    row = repo.get("alice", "followup", result.receipt["id"])
    assert row["event_at"] == "2026-10-21" and row["original_expression"] == "下周三"
    assert row["source_refs"][0]["quote"] == h.source["content"]
    with repo.transaction("alice") as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {}").format(
                repo.table("delivery_outbox")
            )
        )
        assert count.fetchone()["n"] == 0


def test_actual_agent_runtime_injects_parser_and_commits_the_real_memory(
    repo: PostgresRepository,
) -> None:
    run = queued(repo, "我下周三参加面试，请记住")
    arguments = dict(writer(run), kind="event")
    port = ScriptedPort(
        [
            answer("", [ToolCall("remember-date", "memory_write", arguments)]),
            answer("记好了〔f1〕"),
        ]
    )
    result, _ = invoke(repo, run, port)
    assert result["schema"] == "core4.0"
    fact = repo.list("alice", "fact")[0]
    assert (
        fact["event_at"] == "2026-10-21"
        and fact["content"] == run["request"]["message"]
    )


def test_scripted_dc01_exposes_real_date_result_and_r4_safe_status(
    repo: PostgresRepository,
) -> None:
    run = queued(repo, "下周三面试还有几天？")
    port = ScriptedPort(
        [
            answer(
                "",
                [
                    ToolCall(
                        "date-check",
                        "date_calc",
                        {"op": "diff", "a": "2026-10-17", "b": "2026-10-21"},
                    )
                ],
            ),
            answer("还有4天，下周三（10/21 周三）。"),
        ]
    )
    result, events = invoke(repo, run, port)
    assert "下周三（10/21 周三）" in result["text"]
    tool_events = [event["data"] for event in events if event["type"] == "tool_result"]
    assert len(tool_events) == 1 and tool_events[0]["name"] == "date_calc"
    assert tool_events[0]["summary"] == "算了一下日期" and "10/21" not in str(
        tool_events
    )
    specs = port.requests[0]["tools"]
    assert "date_calc" in {tool.name for tool in specs} and len(specs) <= 15
    assert any(
        "紧跟相对说法后加括号" in message.content
        for message in port.requests[0]["messages"]
    )

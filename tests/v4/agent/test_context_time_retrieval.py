"""Time windows are source-relative and ambiguous seasons do not become whole years."""

from __future__ import annotations

from datetime import datetime

import pytest

from mingjing_core.agent.context_time_retrieval import time_window
from mingjing_core.application.time_range_parser import ModuleTimeRangeParser

SOURCE = {"at": "2026-10-17T10:30:00+08:00"}


@pytest.mark.parametrize(
    "query,expected",
    [
        ("昨天", "2026-10-16..2026-10-16"),
        ("前天", "2026-10-15..2026-10-15"),
        ("上周", "2026-10-05..2026-10-11"),
        ("上个月", "2026-09-01..2026-09-30"),
        ("去年", "2025-01-01..2025-12-31"),
        ("国庆那几天", "2026-10-01..2026-10-07"),
        ("最近三天", "2026-10-15..2026-10-17"),
        ("最近一天", "2026-10-17..2026-10-17"),
        ("2026-10-03", "2026-10-03..2026-10-03"),
        ("下周三", "2026-10-21..2026-10-21"),
    ],
)
def test_real_parser_window(query: str, expected: str) -> None:
    result = time_window(ModuleTimeRangeParser(), query, SOURCE, "Asia/Shanghai")
    assert result and result.label == expected


@pytest.mark.parametrize("query", ["去年冬天", "今年春天", "最近", "以前", "那时候", "下学期", "每周三"])
def test_ambiguous_window_does_not_silently_filter(query: str) -> None:
    assert time_window(ModuleTimeRangeParser(), query, SOURCE, "Asia/Shanghai") is None


def test_window_ends_exclusively_and_uses_owner_zone_for_event_dates() -> None:
    result = time_window(ModuleTimeRangeParser(), "昨天", SOURCE, "Asia/Shanghai")
    assert result and result.matches({"at": "2026-10-16T15:59:59+00:00"})
    assert not result.matches({"at": "2026-10-16T16:00:00+00:00"})
    assert result.matches({"_retrieval_kind": "fact", "event_at": "2026-10-16", "said_at": SOURCE["at"]})
    assert not result.matches({"_retrieval_kind": "fact", "event_at": "2026-10-17", "said_at": SOURCE["at"]})


def test_naive_or_missing_source_time_cannot_be_a_new_execution_reference() -> None:
    with pytest.raises(ValueError):
        ModuleTimeRangeParser().parse_time_range("昨天", datetime(2026, 10, 17))
    with pytest.raises(ValueError):
        time_window(ModuleTimeRangeParser(), "昨天", {"at": None}, "Asia/Shanghai")


def test_candidate_budget_and_missing_exact_quote_are_safe() -> None:
    from types import SimpleNamespace

    from mingjing_core.agent.context_time_retrieval import retrieve

    calls = []

    def search(owner, subject, tokens, kinds, limit):
        calls.append((kinds[0], limit))
        return [{"id": f"{kinds[0]}-{index}"} for index in range(limit)]

    sources = SimpleNamespace(
        time_parser=ModuleTimeRangeParser(),
        repo=SimpleNamespace(search=search),
        policy=SimpleNamespace(search_limit=5),
        _project=lambda *args: None,
    )
    facts = [
        {"id": f"fact-{index}", "content": "合成正文", "source_refs": [{"quote": "不同的原话"}]} for index in range(5)
    ]
    result, candidates, window = retrieve(
        sources, "alice", "self", "合成问题", facts, (), {"id": "current", **SOURCE}, "Asia/Shanghai"
    )
    assert result == [] and candidates == 10 and window is None
    assert calls == [("message", 5), ("fact", 5)]

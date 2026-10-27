"""Recorder correctness uses synthetic counts and injected clocks, not a timing threshold."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.mod_week.performance import ROOT, measure, write_report


def test_clock_explicit_timezone_and_source_digest():
    destination = ROOT / "private/mod-week/perf-recorder-test.json"
    report = write_report(
        destination,
        [{"name": "synthetic"}],
        [Path(__file__)],
        clock=FrozenClock(datetime(2026, 10, 20, 23, tzinfo=UTC)),
    )
    assert report["observed_at"] == "2026-10-21T07:00:00+08:00"
    assert "test_performance_mod.py" in next(iter(report["source_sha256"]))


def test_outside_workspace_rejected():
    with pytest.raises(ValueError, match="工作目录"):
        write_report(ROOT.parent / "never-written.json", [], [], clock=FrozenClock(datetime(2026, 1, 1, tzinfo=UTC)))


def test_varying_workload_not_reported_as_equal():
    counts = iter([1, 2])
    with pytest.raises(ValueError, match="工作量不稳定"):
        measure("unstable", lambda: next(counts), repeats=3)

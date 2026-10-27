"""A generated readiness summary cannot turn absent product observations into passes."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.eval_material_v23.loader import MaterialError, load_materials
from tools.eval_material_v23.report import build_readiness


def test_no_observation_report_lists_exact_fixed_blocks_and_zero_passes() -> None:
    at = datetime(2026, 10, 20, 23, 30, tzinfo=UTC)
    first = build_readiness(load_materials(), clock=FrozenClock(at))
    other = build_readiness(load_materials(), clock=FrozenClock(at.astimezone(ZoneInfo("Asia/Tokyo"))))
    assert first == other
    assert first["generated_at"] == "2026-10-21T07:30:00+08:00"
    assert first["counts"] == {"unverified": 51, "blocked_decision": 1, "blocked_dependency": 7, "observed_pass": 0}
    assert first["case_count"] == 59 and first["assertion_count"] == 189


def test_readiness_report_rejects_a_host_naive_clock() -> None:
    class NaiveClock:
        def now(self) -> datetime:
            return datetime(2026, 10, 21, 7, 30)

    with pytest.raises(MaterialError, match="report_clock_must_be_aware"):
        build_readiness(load_materials(), clock=NaiveClock())

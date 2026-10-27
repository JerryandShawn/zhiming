"""The 28 public cases frozen in MOD_scheduling_public_boundaries_calendar_20261021.md.

Only injected local ports and explicit clocks are used. No private iterator or frozen state is patched.
"""

from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.scheduling import NextTriggerResult, RecurrenceError, RecurrenceRule, next_trigger
from mingjing_core.timekit.calendar_cn import DayStatus
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.timeparse.calendar_port import CalendarPort

REFERENCE = datetime(2026, 10, 17, tzinfo=ZoneInfo("Asia/Shanghai"))
MARKER = "SYNTHETIC_CALENDAR_RESOURCE_MARKER"


class StatusPort:
    """A trusted-host port can still report malformed local resource data or an I/O failure."""

    def __init__(self, status: DayStatus, *, error: Exception | None = None) -> None:
        self.status = status
        self.error = error
        self.calls: list[date] = []

    def day_status(self, day: date) -> DayStatus:
        self.calls.append(day)
        if self.error is not None:
            raise self.error
        return self.status


class LunarPort:
    """Explicit synthetic conversion output; it makes no assertion about actual lunar astronomy."""

    def __init__(self, answer: object, *, error: Exception | None = None, absent_before: int | None = None) -> None:
        self.answer = answer
        self.error = error
        self.absent_before = absent_before
        self.calls: list[tuple[int, int, int, bool]] = []

    def lunar_date(self, year: int, month: int, day: int, leap: bool = False) -> object:
        self.calls.append((year, month, day, leap))
        if self.error is not None:
            raise self.error
        if self.absent_before is not None and year < self.absent_before:
            raise LookupError("SYNTHETIC_ABSENT_LUNAR_DATE")
        return self.answer


def invoke(rule: RecurrenceRule, port: object, at: datetime = REFERENCE) -> NextTriggerResult:
    clock = FrozenClock(at)
    return next_trigger(rule, clock.now(), cast(CalendarPort, port))


def assert_unavailable(result: NextTriggerResult, reason: str) -> None:
    assert result.at is None and result.needs_clarification and result.candidates == ()
    assert result.reason == reason
    assert MARKER not in repr(result)


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(DayStatus("workday", None, False, "unknown"), id="CA01-unknown-source"),
        pytest.param(DayStatus("holiday", None, 1, "override"), id="CA02-integer-off-flag"),
        pytest.param(DayStatus("unknown", None, False, "override"), id="CA03-unknown-kind"),
        pytest.param(DayStatus("holiday", None, False, "override"), id="CA04-holiday-not-off"),
        pytest.param(DayStatus("adjusted_workday", None, True, "override"), id="CA05-makeup-is-off"),
    ],
)
def test_malformed_calendar_status_never_authorizes_a_workday(status: DayStatus) -> None:
    port = StatusPort(status)
    result = invoke(RecurrenceRule("workday", time(9)), port)
    assert_unavailable(result, "calendar_status_invalid")
    assert port.calls == [REFERENCE.date()]


def test_day_status_io_failure_is_safe_without_marker_or_weekday_fallback() -> None:
    port = StatusPort(DayStatus("workday", None, False, "override"), error=OSError(MARKER))
    assert_unavailable(invoke(RecurrenceRule("workday", time(9)), port), "calendar_unavailable")
    assert port.calls == [REFERENCE.date()]


def test_missing_day_status_method_is_not_a_default_workday() -> None:
    assert_unavailable(invoke(RecurrenceRule("workday", time(9)), SimpleNamespace()), "calendar_unavailable")


def test_daily_rule_does_not_consult_an_unneeded_broken_holiday_port() -> None:
    port = StatusPort(DayStatus("workday", None, False, "override"), error=AssertionError(MARKER))
    result = invoke(RecurrenceRule("daily", time(9)), port)
    assert result.at == datetime(2026, 10, 17, 1, tzinfo=UTC)
    assert not result.needs_clarification and result.calendar_source is None and port.calls == []


@pytest.mark.parametrize(
    "answer",
    [pytest.param(datetime(2026, 2, 17, tzinfo=UTC), id="CL01-datetime"), pytest.param(None, id="CL02-none")],
)
def test_lunar_port_requires_an_exact_civil_date(answer: object) -> None:
    rule = RecurrenceRule("lunar_yearly", time(9), month=1, day=1)
    assert_unavailable(invoke(rule, LunarPort(answer)), "lunar_calendar_result_invalid")


def test_lunar_port_io_failure_is_not_an_absent_lunar_day() -> None:
    port = LunarPort(None, error=OSError(MARKER))
    rule = RecurrenceRule("lunar_yearly", time(9), month=1, day=1)
    assert_unavailable(invoke(rule, port), "lunar_calendar_unavailable")
    assert len(port.calls) == 1


def test_missing_lunar_method_does_not_become_a_civil_anniversary() -> None:
    rule = RecurrenceRule("lunar_yearly", time(9), month=1, day=1)
    assert_unavailable(invoke(rule, SimpleNamespace()), "lunar_calendar_unavailable")


@pytest.mark.parametrize("year", [pytest.param(1899, id="CL05-below"), pytest.param(2201, id="CL06-above")])
def test_lunar_support_year_boundaries_are_checked_before_port_calls(year: int) -> None:
    port = LunarPort(None, error=AssertionError(MARKER))
    rule = RecurrenceRule("lunar_yearly", time(9), month=1, day=1)
    reference = datetime(year, 6, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    assert_unavailable(invoke(rule, port, reference), "lunar_calendar_year_outside_supported_range")
    assert port.calls == []


def test_absent_lunar_candidate_is_skipped_without_discarding_the_port() -> None:
    port = LunarPort(date(2026, 2, 17), absent_before=2026)
    rule = RecurrenceRule("lunar_yearly", time(9), month=1, day=1)
    result = invoke(rule, port, datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert result.at == datetime(2026, 2, 17, 1, tzinfo=UTC)
    assert not result.needs_clarification and result.calendar_source == "p2_lunar"
    assert port.calls == [(2025, 1, 1, False), (2026, 1, 1, False)]


@pytest.mark.parametrize(
    "fields,reason",
    [
        pytest.param({"kind": "monthly"}, "month_day_required", id="CC01-monthly-no-day"),
        pytest.param({"kind": "yearly", "day": 1}, "year_month_required", id="CC02-yearly-no-month"),
        pytest.param({"kind": "daily", "leap": True}, "leap_only_for_annual_lunar_rule", id="CC03-wrong-leap"),
        pytest.param({"kind": "workday", "day_filter": "offday"}, "conflicting_day_filter", id="CC04-conflict"),
        pytest.param({"kind": "daily", "day": 1}, "rule_field_not_applicable", id="CC05-extra-day"),
    ],
)
def test_public_rule_semantic_conflicts_are_rejected(fields: dict[str, object], reason: str) -> None:
    with pytest.raises(RecurrenceError) as caught:
        RecurrenceRule(local_time=time(9), **fields)
    assert caught.value.reason_code == reason


def test_public_result_requires_a_real_clarification_boolean() -> None:
    with pytest.raises(RecurrenceError) as caught:
        NextTriggerResult(None, needs_clarification=1)
    assert caught.value.reason_code == "clarification_flag_invalid"


@pytest.mark.parametrize(
    "rule",
    [
        pytest.param(RecurrenceRule("daily", time(23, 59, 59), "UTC"), id="CV01-daily"),
        pytest.param(RecurrenceRule("monthly", time(23, 59, 59), "UTC", day=31), id="CV02-monthly"),
        pytest.param(RecurrenceRule("yearly", time(9), "UTC", month=2, day=29), id="CV03-yearly-leap"),
    ],
)
def test_civil_upper_bound_exhausts_without_overflow_or_clamping(rule: RecurrenceRule) -> None:
    clock = FrozenClock(datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC))
    assert_unavailable(next_trigger(rule, clock.now()), "search_horizon_exhausted")


@pytest.mark.parametrize(
    "display_zone", [pytest.param("UTC", id="TZ01-utc"), pytest.param("Asia/Tokyo", id="TZ02-tokyo")]
)
def test_p2_receives_the_rule_local_date_across_the_international_date_line(display_zone: str) -> None:
    clock = FrozenClock(datetime(2026, 10, 17, 10, tzinfo=UTC))
    reference = clock.now().astimezone(ZoneInfo(display_zone))
    port = StatusPort(DayStatus("adjusted_workday", None, False, "override"))
    rule = RecurrenceRule("workday", time(0, 30), "Pacific/Kiritimati")
    result = next_trigger(rule, reference, cast(CalendarPort, port))
    assert result.at == datetime(2026, 10, 17, 10, 30, tzinfo=UTC)
    assert result.calendar_source == "override" and not result.needs_clarification
    assert port.calls == [date(2026, 10, 18)]


def test_remaining_future_dst_fold_does_not_silently_choose_a_policy() -> None:
    clock = FrozenClock(datetime(2026, 11, 1, 5, 45, tzinfo=UTC))
    result = next_trigger(RecurrenceRule("daily", time(1, 30), "America/New_York"), clock.now())
    assert result.at is None and result.needs_clarification and result.reason == "ambiguous_local_time"
    assert result.candidates == (datetime(2026, 11, 1, 6, 30, tzinfo=UTC),)
    assert all(candidate > clock.now() for candidate in result.candidates)


def test_skipped_half_hour_gap_does_not_ask_p2_to_authorize_a_nonexistent_trigger() -> None:
    clock = FrozenClock(datetime(2026, 10, 3, 3, tzinfo=ZoneInfo("Australia/Lord_Howe")))
    port = StatusPort(DayStatus("workday", None, False, "override"))
    rule = RecurrenceRule("daily", time(2, 15), "Australia/Lord_Howe", day_filter="workday", gap_policy="skip")
    result = next_trigger(rule, clock.now(), cast(CalendarPort, port))
    assert result.at == datetime(2026, 10, 4, 15, 15, tzinfo=UTC)
    assert not result.needs_clarification and result.calendar_source == "override"
    assert port.calls == [date(2026, 10, 5)]

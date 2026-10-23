"""Offline recurrence checks: calendar authority, missing days, and actual UTC wall instants."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.scheduling.recurrence import next_trigger, parse_recurrence
from mingjing_core.scheduling.recurrence_contracts import RecurrenceError, RecurrenceRule
from mingjing_core.timekit.calendar_cn import DayStatus
from mingjing_core.timeparse.calendar_port import P2CalendarPort

BJT = ZoneInfo("Asia/Shanghai")


def at(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=BJT)


@pytest.mark.parametrize("inclusive,expected", [(False, at(2026, 10, 18, 9)), (True, at(2026, 10, 17, 9))])
def test_equal_trigger_is_strictly_next_unless_explicit_inclusive(inclusive, expected):
    rule = RecurrenceRule("daily", time(9))
    result = next_trigger(rule, at(2026, 10, 17, 9), inclusive=inclusive)
    assert result.at == expected and result.at.tzinfo == UTC


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("weekly:weekday=2", at(2026, 10, 21, 9)),
        ("monthly:day=31;missing=skip", at(2026, 10, 31, 9)),
        ("yearly:month=2;day=29;missing=skip", at(2028, 2, 29, 9)),
        ("daily", at(2026, 10, 17, 9)),
    ],
)
def test_machine_strings_from_u4_bind_an_explicit_clock(expression, expected):
    rule = parse_recurrence(expression, local_time=time(9))
    assert next_trigger(rule, at(2026, 10, 17)).at == expected
    result = next_trigger(expression, at(2026, 10, 17))
    assert result.at is None and result.needs_clarification and result.reason == "local_time_required"


def test_monthly_missing_date_is_skipped_not_clamped():
    rule = RecurrenceRule("monthly", time(9), day=31)
    assert next_trigger(rule, at(2026, 1, 31, 10)).at == at(2026, 3, 31, 9)
    assert next_trigger(rule, at(2026, 4, 30)).at == at(2026, 5, 31, 9)


def test_workday_respects_national_holiday_and_saturday_makeup_day():
    rule = RecurrenceRule("workday", time(9))
    assert next_trigger(rule, at(2026, 10, 1)).at == at(2026, 10, 8, 9)
    result = next_trigger(rule, at(2026, 10, 9, 10))
    assert result.at == at(2026, 10, 10, 9) and result.calendar_source == "builtin"
    off = next_trigger(RecurrenceRule("offday", time(9)), at(2026, 10, 9, 10))
    assert off.at == at(2026, 10, 11, 9)


def test_unpublished_arrangements_are_not_guessed_but_daily_still_runs():
    calendar = P2CalendarPort()
    ordinary = next_trigger(RecurrenceRule("daily", time(9)), at(2027, 1, 4), calendar)
    unknown = next_trigger(RecurrenceRule("workday", time(9)), at(2027, 1, 4), calendar)
    assert ordinary.at == at(2027, 1, 4, 9)
    assert unknown.at is None and unknown.reason == "calendar_unpublished"


def test_published_override_port_is_used_without_copied_holidays():
    class SyntheticCalendar:
        def day_status(self, day):
            off = day != date(2027, 1, 3)
            return DayStatus("holiday" if off else "adjusted_workday", "合成安排", off, "override")

    result = next_trigger(RecurrenceRule("workday", time(9)), at(2027, 1, 1), SyntheticCalendar())
    assert result.at == at(2027, 1, 3, 9) and result.calendar_source == "override"


def test_monthly_lunar_first_defaults_to_include_leap_sixth_month():
    rule = parse_recurrence("lunar_monthly:day=1;include_leap=true", local_time=time(9))
    assert next_trigger(rule, at(2025, 7, 24, 10)).at == at(2025, 7, 25, 9)
    skipped = next_trigger(replace(rule, include_leap=False), at(2025, 7, 24, 10))
    assert skipped.at == at(2025, 8, 23, 9)


def test_annual_lunar_birthdays_and_explicit_leap_occurrence():
    rule = parse_recurrence("lunar_yearly:month=1;day=1;leap=false", local_time=time(9))
    assert next_trigger(rule, at(2026, 2, 16)).at == at(2026, 2, 17, 9)
    leap = RecurrenceRule("lunar_yearly", time(9), month=6, day=1, leap=True)
    assert next_trigger(leap, at(2025, 7, 24)).at == at(2025, 7, 25, 9)


def test_lunar_day_thirty_skips_small_months_instead_of_rolling_over():
    calendar = P2CalendarPort()
    rule = RecurrenceRule("lunar_monthly", time(9), day=30)
    result = next_trigger(rule, at(2026, 2, 18), calendar)
    assert result.at is not None
    target = result.at.astimezone(BJT).date()
    dates = []
    for month in (1, 2, 3):
        try:
            dates.append(calendar.lunar_date(2026, month, 30))
        except ValueError:
            continue
    assert target == min(day for day in dates if day >= date(2026, 2, 18))


def test_dst_fold_default_exposes_real_two_utc_candidates():
    rule = RecurrenceRule("daily", time(1, 30), "America/New_York")
    threshold = datetime(2026, 11, 1, 4, tzinfo=UTC)
    result = next_trigger(rule, threshold)
    assert result.at is None and result.reason == "ambiguous_local_time"
    assert result.candidates == (datetime(2026, 11, 1, 5, 30, tzinfo=UTC), datetime(2026, 11, 1, 6, 30, tzinfo=UTC))
    assert next_trigger(replace(rule, fold_policy="earliest"), threshold).at == result.candidates[0]
    assert next_trigger(replace(rule, fold_policy="latest"), threshold).at == result.candidates[1]
    after_first = next_trigger(replace(rule, fold_policy="earliest"), result.candidates[0])
    assert after_first.at == datetime(2026, 11, 2, 6, 30, tzinfo=UTC)


def test_dst_gap_default_asks_and_explicit_skip_does_not_shift_clock():
    rule = RecurrenceRule("daily", time(2, 30), "America/New_York")
    threshold = datetime(2026, 3, 8, 5, tzinfo=UTC)
    result = next_trigger(rule, threshold)
    assert result.at is None and result.reason == "nonexistent_local_time"
    assert next_trigger(replace(rule, gap_policy="skip"), threshold).at == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    past_gap = next_trigger(rule, datetime(2026, 3, 8, 8, tzinfo=UTC))
    assert past_gap.at == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "expression",
    [
        "weekly:weekday=True",
        "weekly:weekday=7",
        "monthly:day=0",
        "yearly:month=4;day=31",
        "lunar_monthly:day=31",
        "lunar_yearly:month=13;day=1",
        "daily:unexpected=1",
        "daily:",
        "weekly:weekday=2;weekday=3",
        "monthly:day=31;missing=clamp",
        "lunar_monthly:day=1;include_leap=yes",
    ],
)
def test_invalid_machine_rules_are_rejected_without_raw_text(expression):
    with pytest.raises(RecurrenceError) as caught:
        parse_recurrence(expression, local_time=time(9))
    assert expression not in str(caught.value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"weekday": True},
        {"day": True},
        {"include_leap": 1},
        {"leap": "false"},
        {"time_zone": "Unknown/Zone"},
        {"local_time": time(9, tzinfo=UTC)},
    ],
)
def test_contract_boundaries_fail_closed(kwargs):
    with pytest.raises(RecurrenceError):
        RecurrenceRule("daily", **kwargs)


def test_seeded_weekly_civil_minimality_and_utc_property():
    rng = random.Random(20261021)
    base = at(2026, 1, 1)
    for _ in range(1000):
        reference = base + timedelta(minutes=rng.randrange(365 * 24 * 60))
        weekday, hour = rng.randrange(7), rng.randrange(24)
        rule = RecurrenceRule("weekly", time(hour), weekday=weekday)
        result = next_trigger(rule, reference)
        local = result.at.astimezone(BJT)
        assert result.at > reference and local.weekday() == weekday and local.hour == hour
        assert result.at - reference <= timedelta(days=7)
        prior = result.at - timedelta(days=7)
        assert prior <= reference and result.at.tzinfo == UTC

"""Independent ISO, leap-year, DST and half-open period expectations frozen before these tests."""

import calendar
import hashlib
import random
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reports_v2 import ReportEffects, ReportError, period_for
from mingjing_core.timekit.clock import FrozenClock

from .calendar_acceptance_support_mod import DAY, NOW, ROOT, expected, record, rendered, report


@pytest.mark.parametrize("row", expected()["period_cases"], ids=lambda row: row["id"])
def test_frozen_real_period_examples(row: dict[str, Any]) -> None:
    result = period_for(row["kind"], date.fromisoformat(row["day"]), row["timezone"])
    assert result.key == row["key"]
    assert result.start_day.isoformat() == row["start_day"]
    assert result.end_day.isoformat() == row["end_day"]
    assert result.days == row["calendar_days"]
    assert (result.end - result.start).total_seconds() == row["elapsed_hours"] * 3600
    zone = ZoneInfo(row["timezone"])
    assert result.start == datetime.combine(result.start_day, time(), zone).astimezone(UTC)
    assert result.end == datetime.combine(result.end_day + timedelta(days=1), time(), zone).astimezone(UTC)


def test_frozen_legacy_source_was_not_changed() -> None:
    descriptor = expected()["authoritative_legacy_source"]
    assert hashlib.sha256((ROOT / descriptor["path"]).read_bytes()).hexdigest() == descriptor["sha256"]


def independent_bounds(kind: str, day: date) -> tuple[date, date, str]:
    if kind == "weekly":
        first = day - timedelta(days=day.isoweekday() - 1)
        iso_year, week, _ = day.isocalendar()
        return first, first + timedelta(days=6), f"{iso_year:04d}-W{week:02d}"
    first_month = day.month if kind == "monthly" else 3 * ((day.month - 1) // 3) + 1
    last_month = first_month if kind == "monthly" else first_month + 2
    key = f"{day.year:04d}-{day.month:02d}" if kind == "monthly" else f"{day.year:04d}-Q{first_month // 3 + 1}"
    return date(day.year, first_month, 1), date(day.year, last_month, calendar.monthrange(day.year, last_month)[1]), key


def test_500_independent_random_calendar_periods() -> None:
    rng = random.Random(3305)
    for _ in range(500):
        day = date(2020, 1, 1) + timedelta(days=rng.randrange((date(2031, 1, 1) - date(2020, 1, 1)).days))
        kind = rng.choice(("weekly", "monthly", "quarterly"))
        tz = rng.choice(("Asia/Shanghai", "America/New_York", "Europe/Berlin", "Pacific/Auckland"))
        first, last, key = independent_bounds(kind, day)
        result = period_for(kind, day, tz)
        assert (result.start_day, result.end_day, result.key) == (first, last, key)
        assert first <= day <= last
        assert result.start.astimezone(ZoneInfo(tz)).date() == first
        assert result.end.astimezone(ZoneInfo(tz)).date() == last + timedelta(days=1)


@pytest.mark.parametrize("kind", ("weekly", "monthly", "quarterly"))
@pytest.mark.parametrize("tz", ("Asia/Shanghai", "America/New_York", "Europe/Berlin"))
def test_point_boundary_is_half_open(kind: str, tz: str) -> None:
    period = period_for(kind, DAY, tz)
    clock = FrozenClock(period.end + timedelta(days=1))
    for at, included in (
        (period.start - timedelta(microseconds=1), False),
        (period.start, True),
        (period.end - timedelta(microseconds=1), True),
        (period.end, False),
    ):
        row = record(at=at)
        result = report(kind=kind, timezone=tz, records=(row,), clock=clock)
        assert (row.id in result.used_record_ids) is included
        assert (row.text in rendered(result)) is included


@pytest.mark.parametrize("kind", ("weekly", "monthly", "quarterly"))
@pytest.mark.parametrize("offset_start,offset_end,included", ((-2, 0, False), (-1, 1, True), (0, 1, True)))
def test_nonempty_range_overlap(kind: str, offset_start: int, offset_end: int, included: bool) -> None:
    period = period_for(kind, DAY)
    row = record(at=period.start + timedelta(hours=offset_start), end=period.start + timedelta(hours=offset_end))
    result = report(kind=kind, records=(row,))
    assert (row.id in result.used_record_ids) is included


def test_original_event_time_and_said_at_are_retained_in_utc() -> None:
    original_at = datetime(2026, 10, 21, 9, tzinfo=ZoneInfo("Asia/Tokyo"))
    original_said = datetime(2026, 10, 2, 7, tzinfo=ZoneInfo("America/New_York"))
    row = record(at=original_at, said_at=original_said)
    result = report(records=(row,))
    lines = [line for section in result.sections for line in section.lines if row.text in line.text]
    assert len(lines) == 1
    assert lines[0].event_at == original_at.astimezone(UTC)
    assert lines[0].said_at == original_said.astimezone(UTC)
    assert lines[0].event_at != NOW


def test_missing_event_date_uses_original_said_date_not_execution_now() -> None:
    row = record(at=None, said_at=datetime(2026, 9, 30, 15, 59, 59, tzinfo=UTC))
    assert row.id not in report(records=(row,)).used_record_ids
    row = replace(row, said_at=datetime(2026, 9, 30, 16, tzinfo=UTC))
    result = report(records=(row,))
    lines = [line for section in result.sections for line in section.lines if row.text in line.text]
    assert len(lines) == 1
    assert lines[0].event_at is None and lines[0].said_at == row.said_at
    assert "记录于" in lines[0].text


@pytest.mark.parametrize("category", ("fact", "arrangement", "followup"))
def test_categories_group_without_changing_originals(category: str) -> None:
    row = record(category=category, at=datetime(2026, 10, 21, 1, tzinfo=UTC))
    result = report(records=(row,))
    matching = [section for section in result.sections if any(row.text in line.text for line in section.lines)]
    assert len(matching) == 1 and matching[0].category == category
    assert row.at == datetime(2026, 10, 21, 1, tzinfo=UTC)


def test_all_four_effects_are_integer_zero_and_not_permissions() -> None:
    result = report(records=(record(),))
    assert set(asdict(result.effects)) == {"model_calls", "writes", "notifications", "scheduler_mutations"}
    assert all(type(value) is int and value == 0 for value in asdict(result.effects).values())


@pytest.mark.parametrize("field", ("model_calls", "writes", "notifications", "scheduler_mutations"))
@pytest.mark.parametrize("value", (True, 1, -1, 0.0))
def test_effects_reject_false_zero_or_nonzero(field: str, value: object) -> None:
    with pytest.raises(ReportError):
        ReportEffects(**{field: value})

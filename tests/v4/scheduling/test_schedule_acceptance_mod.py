"""Frozen calendar/DST truth and independent wall-date arithmetic for recurrence."""

import json
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.scheduling.recurrence import next_trigger
from mingjing_core.scheduling.recurrence_contracts import (
    RecurrenceError,
    RecurrenceRule,
)
from mingjing_core.timekit.calendar_cn import day_status

TRUTH = json.loads((Path(__file__).parent / "fixtures/schedule_expected_mod.json").read_bytes())
AT = datetime(2026, 10, 17, tzinfo=UTC)


def rule_for(case):
    extras = {key: case[key] for key in ("weekday", "day", "month", "include_leap") if key in case}
    return RecurrenceRule(case["kind"], time.fromisoformat(case["time"]), case["timezone"], **extras)


@pytest.mark.parametrize("case", TRUTH["cases"], ids=lambda item: item["id"])
def test_fixed_calendar_cases_keep_exact_dates_and_utc_instants(case):
    after = datetime.fromisoformat(case["after"])
    result = next_trigger(rule_for(case), after, inclusive=case.get("inclusive", False))
    assert result.at == datetime.fromisoformat(case["expected"])
    assert not result.needs_clarification
    assert result.at.tzinfo is UTC
    assert result.at >= after if case.get("inclusive", False) else result.at > after


@pytest.mark.parametrize("case", TRUTH["ambiguous"], ids=lambda item: item["id"])
def test_unknown_arrangements_and_dst_ambiguity_do_not_invent_a_primary_trigger(case):
    result = next_trigger(rule_for(case), datetime.fromisoformat(case["after"]))
    assert result.at is None and result.needs_clarification
    if "expected_candidates" in case:
        assert set(result.candidates) == {datetime.fromisoformat(item) for item in case["expected_candidates"]}
    if case["id"] == "unpublished-workday":
        assert "unpublished" in result.reason


@pytest.mark.parametrize(
    "policy,expected",
    [
        ("earliest", "2026-11-01T05:30:00+00:00"),
        ("latest", "2026-11-01T06:30:00+00:00"),
    ],
)
def test_fold_requires_explicit_choice_and_maps_to_actual_utc_instants(policy, expected):
    rule = RecurrenceRule("daily", time(1, 30), "America/New_York", fold_policy=policy)
    result = next_trigger(rule, datetime.fromisoformat("2026-10-31T02:00:00-04:00"))
    assert result.at == datetime.fromisoformat(expected) and not result.needs_clarification


def test_explicit_gap_skip_omits_nonexistent_wall_time_without_shifting_minutes():
    rule = RecurrenceRule("daily", time(2, 30), "America/New_York", gap_policy="skip")
    result = next_trigger(rule, datetime.fromisoformat("2026-03-07T03:00:00-05:00"))
    assert result.at == datetime.fromisoformat("2026-03-09T06:30:00+00:00")


def test_a_half_hour_dst_gap_and_fold_remain_explicitly_ambiguous():
    gap = RecurrenceRule("daily", time(2, 15), "Australia/Lord_Howe")
    missing = next_trigger(gap, datetime.fromisoformat("2026-10-03T03:00:00+10:30"))
    assert missing.at is None and missing.needs_clarification and not missing.candidates
    fold = RecurrenceRule("daily", time(1, 45), "Australia/Lord_Howe")
    repeated = next_trigger(fold, datetime.fromisoformat("2026-04-04T03:00:00+11:00"))
    assert repeated.at is None and repeated.needs_clarification
    assert set(repeated.candidates) == {
        datetime.fromisoformat("2026-04-04T14:45:00+00:00"),
        datetime.fromisoformat("2026-04-04T15:15:00+00:00"),
    }


def test_a_missing_local_time_is_a_question_instead_of_an_unrequested_default():
    result = next_trigger(RecurrenceRule("daily"), AT)
    assert result.at is None and result.needs_clarification


@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "hourly"},
        {"weekday": True},
        {"day": True},
        {"include_leap": 1},
        {"time_zone": "Not/AZone"},
        {"local_time": time(7, tzinfo=UTC)},
        {"gap_policy": "guess"},
        {"fold_policy": "automatic"},
    ],
)
def test_invalid_rule_primitives_and_unfrozen_policies_are_rejected(changes):
    values = dict(kind="daily", local_time=time(7))
    values.update(changes)
    with pytest.raises(RecurrenceError):
        RecurrenceRule(**values)


@pytest.mark.parametrize(
    "kind,fields",
    [
        ("weekly", {}),
        ("monthly", {"day": 0}),
        ("yearly", {"month": 4, "day": 31}),
        ("lunar_monthly", {"day": 31}),
    ],
)
def test_impossible_or_incomplete_dates_are_rejected_instead_of_clamped(kind, fields):
    with pytest.raises(RecurrenceError):
        RecurrenceRule(kind, time(7), **fields)


def test_naive_reference_time_is_rejected():
    with pytest.raises(RecurrenceError):
        next_trigger(RecurrenceRule("daily", time(7)), datetime(2026, 10, 17))


def independent_next(rule, after):
    zone = ZoneInfo(rule.time_zone)
    local = after.astimezone(zone)
    if rule.kind == "daily":
        day = local.date()
        expected = datetime.combine(day, rule.local_time, zone)
        if expected <= after:
            expected += timedelta(days=1)
        return expected.astimezone(UTC)
    if rule.kind == "weekly":
        days = (rule.weekday - local.weekday()) % 7
        expected = datetime.combine(local.date() + timedelta(days=days), rule.local_time, zone)
        if expected <= after:
            expected += timedelta(days=7)
        return expected.astimezone(UTC)
    year, month = local.year, local.month
    expected = datetime(year, month, rule.day, rule.local_time.hour, rule.local_time.minute, tzinfo=zone)
    if expected <= after:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        expected = datetime(
            year,
            month,
            rule.day,
            rule.local_time.hour,
            rule.local_time.minute,
            tzinfo=zone,
        )
    return expected.astimezone(UTC)


@pytest.mark.parametrize("seed", range(50))
def test_1000_fixed_seed_daily_weekly_monthly_cases_match_independent_date_arithmetic(
    seed,
):
    rng = Random(449071 + seed)
    origin = datetime(2025, 1, 1, tzinfo=UTC)
    for _ in range(20):
        after = origin + timedelta(seconds=rng.randrange(3 * 365 * 86400))
        kind, zone = (
            rng.choice(("daily", "weekly", "monthly")),
            rng.choice(("UTC", "Asia/Shanghai", "Asia/Kathmandu")),
        )
        fields = (
            {"weekday": rng.randrange(7)}
            if kind == "weekly"
            else {"day": rng.randrange(1, 29)}
            if kind == "monthly"
            else {}
        )
        rule = RecurrenceRule(kind, time(rng.randrange(24), rng.randrange(60)), zone, **fields)
        result = next_trigger(rule, after)
        assert result.at == independent_next(rule, after), (seed, rule, after)
        assert result.at > after and not result.needs_clarification
        # Changing only the reference's display zone cannot change its instant or trigger.
        assert next_trigger(rule, after.astimezone(ZoneInfo("Asia/Tokyo"))).at == result.at


def test_workday_search_uses_p2_adjustment_status_rather_than_weekday_numbers():
    assert day_status(datetime(2026, 10, 10).date()).kind == "adjusted_workday"
    work = RecurrenceRule("workday", time(9))
    off = replace(work, kind="offday")
    origin = datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
    rng = Random(44333)
    for _ in range(100):
        after = origin + timedelta(days=rng.randrange(350), hours=rng.randrange(24))
        for rule in (work, off):
            result = next_trigger(rule, after)
            assert result.at > after
            target = result.at.astimezone(ZoneInfo("Asia/Shanghai"))
            assert day_status(target.date()).is_off == (rule.kind == "offday")
            assert target.time() == time(9)

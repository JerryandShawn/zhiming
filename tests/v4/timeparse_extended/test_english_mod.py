"""Offline English date regression tables with real UTC instants and explicit civil zones."""

import os
import random
import time
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse.english_dates_v2 import parse_english_date
from mingjing_core.timeparse.parser import parse_time_range

REF = datetime(2026, 10, 17, 2, tzinfo=UTC)  # Saturday 10:00 in Shanghai.
SHANGHAI = ZoneInfo("Asia/Shanghai")
REFERENCES = (
    (REF, "Asia/Shanghai"),
    (datetime(2026, 12, 31, 15, 45, tzinfo=UTC), "Asia/Shanghai"),
    (datetime(2026, 2, 16, 4, tzinfo=UTC), "Asia/Shanghai"),
    (datetime(2025, 7, 25, 12, tzinfo=UTC), "Asia/Shanghai"),
    (datetime(2024, 2, 28, 22, tzinfo=UTC), "Asia/Shanghai"),
    (datetime(2026, 3, 8, 6, tzinfo=UTC), "America/New_York"),
)


def local_day(result, zone="Asia/Shanghai"):
    return result.start.astimezone(ZoneInfo(zone)).date()


@pytest.mark.parametrize("ref,zone", REFERENCES)
@pytest.mark.parametrize(
    "phrase,offset",
    [("today", 0), ("tomorrow", 1), ("yesterday", -1), ("day after tomorrow", 2), ("day before yesterday", -2)],
)
def test_relative_days_preserve_local_civil_date(ref, zone, phrase, offset):
    text = f"计划 {phrase} 面试"
    result = parse_english_date(text, ref, zone)
    expected = ref.astimezone(ZoneInfo(zone)).date() + timedelta(days=offset)
    assert local_day(result, zone) == expected
    assert result.end.astimezone(ZoneInfo(zone)).date() == expected + timedelta(days=1)
    assert not result.needs_clarification
    assert result.original_text == text and text[slice(*result.span)] == phrase


WEEK_CASES = [
    ("this week", "2026-10-12", "2026-10-19"),
    ("next week", "2026-10-19", "2026-10-26"),
    ("following week", "2026-10-19", "2026-10-26"),
    ("last week", "2026-10-05", "2026-10-12"),
    ("weekend", "2026-10-17", "2026-10-19"),
    ("this weekend", "2026-10-17", "2026-10-19"),
    ("next weekend", "2026-10-24", "2026-10-26"),
    ("last weekend", "2026-10-10", "2026-10-12"),
]
for prefix, anchor in (
    ("this", date(2026, 10, 12)),
    ("next", date(2026, 10, 19)),
    ("following", date(2026, 10, 19)),
    ("last", date(2026, 10, 5)),
):
    for number, weekday in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")):
        day = anchor + timedelta(days=number)
        WEEK_CASES.append((f"{prefix} week {weekday}", day.isoformat(), (day + timedelta(days=1)).isoformat()))


@pytest.mark.parametrize("phrase,start,end", WEEK_CASES)
def test_monday_week_and_weekend_tables(phrase, start, end):
    result = parse_english_date(phrase, REF)
    assert local_day(result).isoformat() == start
    assert result.end.astimezone(SHANGHAI).date().isoformat() == end
    assert not result.needs_clarification


@pytest.mark.parametrize(
    "weekday,expected",
    [
        ("Monday", "2026-10-19"),
        ("Tuesday", "2026-10-20"),
        ("Wednesday", "2026-10-21"),
        ("Thursday", "2026-10-22"),
        ("Friday", "2026-10-23"),
        ("Saturday", "2026-10-24"),
        ("Sunday", "2026-10-25"),
    ],
)
def test_weekday_after_explicit_next_week_is_fixed(weekday, expected):
    result = parse_english_date(f"{weekday} next week", REF)
    assert local_day(result).isoformat() == expected and not result.needs_clarification


@pytest.mark.parametrize("weekday", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
def test_next_weekday_is_always_explicitly_ambiguous(weekday):
    result = parse_english_date(f"next {weekday}", REF)
    assert result.needs_clarification and result.candidates
    assert result.start is None


@pytest.mark.parametrize("amount", [1, 2, 3, 7, 14, 21, 30])
@pytest.mark.parametrize("unit,days", [("days", 1), ("weeks", 7)])
@pytest.mark.parametrize("direction", ["in", "within"])
def test_duration_tables(amount, unit, days, direction):
    result = parse_english_date(f"{direction} {amount} {unit}", REF)
    target = REF.astimezone(SHANGHAI) + timedelta(days=amount * days)
    if direction == "within":
        assert result.kind == "range" and result.start == REF
        assert result.end == target.astimezone(UTC)
    else:
        assert local_day(result) == target.date()
    assert not result.needs_clarification


@pytest.mark.parametrize(
    "month,number",
    [
        ("January", 1),
        ("February", 2),
        ("March", 3),
        ("April", 4),
        ("May", 5),
        ("June", 6),
        ("July", 7),
        ("August", 8),
        ("September", 9),
        ("October", 10),
        ("November", 11),
        ("December", 12),
    ],
)
def test_all_english_month_names(month, number):
    result = parse_english_date(f"{month} 15, 2027", REF)
    assert local_day(result) == date(2027, number, 15)
    assert not result.needs_clarification


@pytest.mark.parametrize(
    "text,expected",
    [
        ("15th Feb 2028", "2028-02-15"),
        ("1st March 2027", "2027-03-01"),
        ("2nd Apr. 2027", "2027-04-02"),
        ("Sept 3rd, 2027", "2027-09-03"),
        ("2024-02-29", "2024-02-29"),
        ("13/04/2026", "2026-04-13"),
        ("04/13/2026", "2026-04-13"),
        ("04/04/2026", "2026-04-04"),
    ],
)
def test_absolute_formats_and_unique_numeric_order(text, expected):
    result = parse_english_date(text, REF)
    assert local_day(result).isoformat() == expected and not result.needs_clarification


@pytest.mark.parametrize(
    "text",
    [
        "2026-02-29",
        "February 30, 2026",
        "2026-13-01",
        "32/13/2026",
        "April 31, 2026",
        "in 0 days",
        "within -2 days",
        "in 1.5 weeks",
        "Q5",
        "today 25:00",
        "today 13pm",
    ],
)
def test_invalid_expressions_are_not_partially_accepted(text):
    result = parse_english_date(text, REF)
    assert result is not None and result.needs_clarification


@pytest.mark.parametrize("hour", list(range(1, 13)))
@pytest.mark.parametrize("period", ["am", "pm"])
def test_twelve_hour_clock_table(hour, period):
    result = parse_english_date(f"tomorrow at {hour}:30 {period}", REF)
    expected_hour = hour % 12 + (12 if period == "pm" else 0)
    expected = datetime(2026, 10, 18, expected_hour, 30, tzinfo=SHANGHAI).astimezone(UTC)
    assert result.start == result.end == expected and not result.needs_clarification


@pytest.mark.parametrize(
    "text,expected",
    [
        ("tomorrow 下午三点开会", "2026-10-18T07:00:00+00:00"),
        ("明天 at 3pm 面试", "2026-10-18T07:00:00+00:00"),
        ("2026-10-18 3pm UTC", "2026-10-18T15:00:00+00:00"),
        ("2026-10-18 3pm UTC+05:30", "2026-10-18T09:30:00+00:00"),
        ("2026-10-18 3pm America/New_York", "2026-10-18T19:00:00+00:00"),
        ("2026-10-18T15:30:00Z", "2026-10-18T15:30:00+00:00"),
        ("2026-10-18T15:30+08:00", "2026-10-18T07:30:00+00:00"),
    ],
)
def test_mixed_language_and_explicit_timezone_instants(text, expected):
    result = parse_english_date(text, REF)
    assert result.start.isoformat() == expected and result.end == result.start
    assert not result.needs_clarification and text[slice(*result.span)] == result.matched_text


@pytest.mark.parametrize(
    "text,reason",
    [
        ("2026-03-08 02:30 America/New_York", "nonexistent_wall_clock"),
        ("2026-11-01 01:30 America/New_York", "ambiguous_wall_clock"),
    ],
)
def test_dst_gap_and_fold_never_choose_an_instant(text, reason):
    result = parse_english_date(text, REF)
    assert result.start is None and result.needs_clarification and result.reason == reason
    assert len(result.candidates) == 2


@pytest.mark.parametrize(
    "text",
    [
        "today and tomorrow",
        "tomorrow 3pm and 4pm",
        "today 开会，明天面试",
        "tomorrow 下午三点 and 4pm",
        "tomorrow 3pm CST",
        "04/05/2026",
        "January 5",
        "Saturday",
    ],
)
def test_ambiguity_keeps_candidates_and_original_text(text):
    result = parse_english_date(text, REF)
    assert result.needs_clarification and result.candidates
    assert result.original_text == text


@pytest.mark.parametrize(
    "text,first,last",
    [
        ("this quarter", "2026-10-01", "2027-01-01"),
        ("next quarter", "2027-01-01", "2027-04-01"),
        ("last quarter", "2026-07-01", "2026-10-01"),
        ("Q1 2027", "2027-01-01", "2027-04-01"),
        ("2027 Q2", "2027-04-01", "2027-07-01"),
        ("third quarter of 2027", "2027-07-01", "2027-10-01"),
        ("4th quarter 2027", "2027-10-01", "2028-01-01"),
    ],
)
def test_quarter_tables(text, first, last):
    result = parse_english_date(text, REF)
    assert result.kind == "range" and result.granularity == "quarter"
    assert local_day(result).isoformat() == first and result.end.astimezone(SHANGHAI).date().isoformat() == last


@pytest.mark.parametrize(
    "text",
    [
        "hello world",
        "Tomorrowland is a name",
        "may I ask",
        "I work on strategy",
        "一家科技公司",
        "the product is modern",
        "weekending is not a date",
        "quarterback",
        "I have 3pm-style notes",
        "the tomorrow-ish concept",
        "pre-Monday-style planning",
    ],
)
def test_non_temporal_strings_do_not_match(text):
    assert parse_english_date(text, REF) is None


def test_random_dates_preserve_utc_instants_and_original_spans():
    rng = random.Random(20261021)
    for _ in range(300):
        expected = datetime(
            2024 + rng.randrange(8),
            rng.randrange(1, 13),
            rng.randrange(1, 29),
            rng.randrange(24),
            rng.randrange(60),
            tzinfo=UTC,
        )
        stamp = expected.isoformat().replace("+00:00", "Z")
        text = f"备忘 {stamp} 发出提醒"
        result = parse_english_date(text, REF)
        assert result.start == expected and result.end == expected and not result.needs_clarification
        assert text[slice(*result.span)] == stamp and result.original_text == text


def test_process_timezone_does_not_change_results():
    original = os.environ.get("TZ")
    try:
        values = []
        for zone in ("Asia/Tokyo", "UTC", "America/Los_Angeles"):
            os.environ["TZ"] = zone
            if hasattr(time, "tzset"):
                time.tzset()
            values.append(parse_english_date("tomorrow at 3pm", REF).as_dict())
        assert values[0] == values[1] == values[2]
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.mark.parametrize(
    "english,chinese",
    [
        ("New Year's Day", "元旦"),
        ("Chinese New Year", "春节"),
        ("Qingming", "清明"),
        ("Labour Day", "五一"),
        ("Dragon Boat Festival", "端午"),
        ("Mid-Autumn Festival", "中秋"),
        ("National Day", "国庆"),
    ],
)
def test_holiday_label_bridge_delegates_to_existing_p2_calendar(english, chinese):
    text = f"安排 2026 {english} 见面"
    result = parse_english_date(text, REF)
    expected = parse_time_range(f"2026年{chinese}", REF)
    assert (result.start, result.end, result.needs_clarification) == (
        expected.start,
        expected.end,
        expected.needs_clarification,
    )
    assert text[slice(*result.span)] == f"2026 {english}"


@pytest.mark.parametrize("text", ["Q" + "9" * 5000, "today 3pm UTC+999", "today 3:000pm", "today 3pm UTC+8:5"])
def test_malformed_numbers_and_timezone_cannot_be_accepted_in_part(text):
    result = parse_english_date(text, REF)
    assert result is not None and result.needs_clarification


@pytest.mark.parametrize("text", ["tomorrow meeting at 3pm", "tomorrow 开会 下午三点", "3pm meeting tomorrow"])
def test_noncontiguous_date_clock_never_consumes_unparsed_event_words(text):
    result = parse_english_date(text, REF)
    assert result.needs_clarification and result.reason == "noncontiguous_date_clock_spans"
    assert result.original_text == text and result.candidates


@pytest.mark.parametrize(
    "text",
    [
        "every Monday interview",
        "each day exercise",
        "every week at 15:30",
        "each month review",
        "every year anniversary",
        "daily report",
        "weekly review",
        "monthly bill",
        "yearly check",
        "annually check",
        "every other Friday",
        "every 2 weeks",
        "each 周一提醒",
        "every first Monday at 3pm",
        "every working day at 3pm",
        "each morning at 3pm",
    ],
)
def test_unsupported_english_recurrence_is_never_a_single_date(text):
    from mingjing_core.timeparse.extended_v2 import absolutize_extended

    result = parse_english_date(text, REF)
    assert result.kind == "recurring" and result.needs_clarification
    assert result.reason == "unsupported_english_recurrence" and result.recurrence is None
    assert result.start is None and result.end is None and result.candidates
    assert all(value.start is None and value.end is None for value in result.candidates)
    assert result.original_text == text and text[slice(*result.span)] == result.matched_text
    absolute = absolutize_extended(text, REF)
    assert absolute.text == text and not absolute.replaced and absolute.result.needs_clarification


@pytest.mark.parametrize(
    "text",
    [
        "every person has goals",
        "everyday life",
        "dailyish notes",
        "weekly-ish estimates",
        "each of these matters",
        "the monthly-ish theme",
    ],
)
def test_periodic_sounding_words_do_not_invent_recurrence(text):
    assert parse_english_date(text, REF) is None

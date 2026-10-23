"""Independent frozen date expectations and semantic invariants, never parser-derived labels."""

import json
import os
import random
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lunar_python import Lunar, Solar

from mingjing_core.timekit.calendar_cn import day_status, holiday_window, statutory_dates
from mingjing_core.timeparse.parser import absolutize, parse_time_range

ZONE = ZoneInfo("Asia/Shanghai")
MATRIX = json.loads((Path(__file__).parent / "fixtures/u4_acceptance_expected_mod.json").read_text(encoding="utf-8"))
REFS = [datetime.fromisoformat(value) for value in MATRIX["reference_times"]]
BASE = REFS[0]


def local_date(value: datetime) -> date:
    assert value.tzinfo is not None and value.utcoffset() is not None
    return value.astimezone(ZONE).date()


@pytest.mark.parametrize("case", MATRIX["point_cases"], ids=lambda row: row["ref"][:10] + ":" + row["text"])
def test_frozen_clear_day_points(case: dict) -> None:
    result = parse_time_range(case["text"], datetime.fromisoformat(case["ref"]))
    expected = date.fromisoformat(case["date"])
    assert not result.needs_clarification and result.kind == "point"
    assert result.granularity == "day" and result.start is not None and result.end is not None
    assert local_date(result.start) == expected
    assert local_date(result.end) == expected + timedelta(days=1)
    assert result.start.astimezone(ZONE).hour == result.end.astimezone(ZONE).hour == 0
    assert result.start.utcoffset() == result.end.utcoffset() == timedelta(0)
    assert result.original_text == case["text"]
    assert result.normalized_text and result.confidence >= 0.6


@pytest.mark.parametrize("case", MATRIX["period_cases"])
def test_frozen_ten_day_intervals_are_half_open(case: dict) -> None:
    result = parse_time_range(case["text"], datetime.fromisoformat(case["ref"]))
    assert result.kind == "range" and not result.needs_clarification
    assert local_date(result.start).isoformat() == case["start"]
    assert local_date(result.end).isoformat() == case["end"]
    assert result.start < result.end


@pytest.mark.parametrize("text", MATRIX["negative_texts"])
def test_twenty_four_non_time_counterexamples_do_not_invent_dates(text: str) -> None:
    result = parse_time_range(text, BASE)
    assert result.start is None and result.end is None and not result.candidates
    assert result.confidence == 0 and not result.needs_clarification
    absolute = absolutize(text, BASE)
    assert absolute.original_text == absolute.text == text and not absolute.replaced


@pytest.mark.parametrize("text", MATRIX["invalid_texts"])
def test_invalid_time_does_not_leave_a_falsely_certain_partial_match(text: str) -> None:
    result = parse_time_range(text, BASE)
    assert result.needs_clarification or (result.start is None and result.end is None)
    absolute = absolutize(text, BASE)
    assert not absolute.replaced and absolute.original_text == absolute.text == text


@pytest.mark.parametrize("ref", REFS)
@pytest.mark.parametrize("text,position", [("月初", "begin"), ("月中", "middle"), ("月底", "end")])
def test_vague_month_parts_respect_position_without_assuming_a_school_policy(
    ref: datetime, text: str, position: str
) -> None:
    result = parse_time_range(text, ref)
    start, end = local_date(result.start), local_date(result.end)
    assert result.kind == "range" and start < end
    assert (start.year, start.month) == (ref.year, ref.month)
    if position == "begin":
        assert start.day == 1 and end.day <= 11
    elif position == "middle":
        assert start <= ref.date().replace(day=15) < end
    else:
        assert start.day >= 21 and end.day == 1 and end.month == ref.month % 12 + 1


@pytest.mark.parametrize("ref", REFS)
@pytest.mark.parametrize("text,weeks", [("周末", 0), ("下周末", 1)])
def test_weekend_starts_saturday_and_ends_monday(ref: datetime, text: str, weeks: int) -> None:
    monday = date.fromisocalendar(ref.isocalendar().year, ref.isocalendar().week, 1)
    result = parse_time_range(text, ref)
    assert local_date(result.start) == monday + timedelta(weeks=weeks, days=5)
    assert local_date(result.end) == monday + timedelta(weeks=weeks + 1)
    assert result.kind == "range"


@pytest.mark.parametrize(
    "text,hour,minute",
    [
        ("明天下午三点", 15, 0),
        ("明天晚上八点半", 20, 30),
        ("明天凌晨两点", 2, 0),
        ("明天上午九点一刻", 9, 15),
        ("明天中午十二点", 12, 0),
        ("明天早上六点", 6, 0),
        ("明天下午十三点", 13, 0),
    ],
)
def test_precise_clock_points_do_not_shift_the_explicit_civil_day(text: str, hour: int, minute: int) -> None:
    result = parse_time_range(text, BASE)
    local = result.start.astimezone(ZONE)
    assert local.date() == date(2026, 10, 18) and (local.hour, local.minute) == (hour, minute)
    assert result.start == result.end and result.kind == "point"


@pytest.mark.parametrize("ref", REFS)
def test_tonight_two_am_has_today_and_next_day_candidates(ref: datetime) -> None:
    result = parse_time_range("今晚凌晨两点", ref)
    assert result.needs_clarification and len(result.candidates) >= 2
    dates = {local_date(candidate.start) for candidate in result.candidates}
    assert {ref.date(), ref.date() + timedelta(days=1)} <= dates
    assert all(candidate.start.astimezone(ZONE).hour == 2 for candidate in result.candidates)
    assert not absolutize("今晚凌晨两点再确认", ref).replaced


def test_bare_weekday_on_that_weekday_requires_which_week() -> None:
    ref = datetime(2026, 10, 21, 11, tzinfo=ZONE)
    result = parse_time_range("周三", ref)
    assert result.needs_clarification
    assert {local_date(item.start) for item in result.candidates} >= {date(2026, 10, 21), date(2026, 10, 28)}


@pytest.mark.parametrize("ref", REFS)
def test_vague_few_days_is_low_confidence_and_not_written_as_an_exact_fact(ref: datetime) -> None:
    result = parse_time_range("过几天", ref)
    assert result.needs_clarification and result.confidence < 0.8
    assert result.start is not None and result.end is not None and result.start < result.end
    assert result.kind == "range" and not absolutize("过几天去看看", ref).replaced


@pytest.mark.parametrize("ref", REFS)
@pytest.mark.parametrize("text,target_hour", [("中午", 12), ("傍晚", 18)])
def test_named_time_of_day_contains_the_named_period(ref: datetime, text: str, target_hour: int) -> None:
    result = parse_time_range(text, ref)
    assert local_date(result.start) == ref.date()
    start, end = result.start.astimezone(ZONE), result.end.astimezone(ZONE)
    if result.kind == "point":
        assert start.hour == target_hour and start == end
    else:
        assert start.hour <= target_hour < end.hour


@pytest.mark.parametrize("ref", REFS)
def test_within_two_weeks_is_a_range_not_a_single_due_day(ref: datetime) -> None:
    result = parse_time_range("两周内", ref)
    assert result.kind == "range" and local_date(result.start) == ref.date()
    assert local_date(result.end) == ref.date() + timedelta(days=14)
    assert result.start <= ref <= result.end


@pytest.mark.parametrize("ref", REFS)
@pytest.mark.parametrize("text,offset", [("这季度", 0), ("下季度", 1)])
def test_calendar_quarters_cover_three_months_and_cross_year(ref: datetime, text: str, offset: int) -> None:
    ordinal = ref.year * 4 + (ref.month - 1) // 3 + offset
    year, quarter = divmod(ordinal, 4)
    expected_start = date(year, quarter * 3 + 1, 1)
    next_year, next_quarter = divmod(ordinal + 1, 4)
    expected_end = date(next_year, next_quarter * 3 + 1, 1)
    result = parse_time_range(text, ref)
    assert result.kind == "range" and local_date(result.start) == expected_start
    assert local_date(result.end) == expected_end


@pytest.mark.parametrize("text", ["春季学期", "秋季学期", "本学期", "下学期"])
def test_school_semesters_require_calendar_confirmation(text: str) -> None:
    result = parse_time_range(text, BASE)
    assert result.needs_clarification and result.confidence < 0.8
    assert result.candidates or (result.start is not None and result.end is not None)
    assert not absolutize(text + "准备考试", BASE).replaced


@pytest.mark.parametrize("holiday", ["春节", "国庆", "清明", "五一", "端午", "中秋", "元旦"])
@pytest.mark.parametrize("side", ["前", "后"])
def test_unbounded_holiday_horizons_offer_candidates_without_inventing_a_deadline(holiday: str, side: str) -> None:
    text = "2026年" + holiday + side
    result = parse_time_range(text, BASE)
    assert result.needs_clarification and result.confidence < 0.8 and len(result.candidates) >= 2
    assert all(
        candidate.start is not None and candidate.end is not None and candidate.start < candidate.end
        for candidate in result.candidates
    )
    assert not absolutize(text + "再联系", BASE).replaced


@pytest.mark.parametrize("text", ["年前", "年后", "春节前后"])
def test_year_boundary_language_keeps_calendar_or_horizon_ambiguity(text: str) -> None:
    result = parse_time_range(text, BASE)
    assert result.needs_clarification and len(result.candidates) >= 2
    assert not absolutize(text + "处理这件事", BASE).replaced


@pytest.mark.parametrize("text", ["春节", "国庆", "清明", "五一", "端午", "中秋", "元旦"])
def test_published_holiday_periods_match_p2_read_only_source(text: str) -> None:
    ref = datetime(2026, 1, 1, 10, tzinfo=ZONE)
    names = {
        "春节": "春节",
        "国庆": "国庆节",
        "清明": "清明节",
        "五一": "劳动节",
        "端午": "端午节",
        "中秋": "中秋节",
        "元旦": "元旦",
    }
    anchor = next(day for day, name in statutory_dates(2026) if name == names[text])
    window = holiday_window(anchor)
    assert window is not None
    result = parse_time_range("2026年" + text + "期间", ref)
    assert local_date(result.start) == window[0]
    assert local_date(result.end) == window[1] + timedelta(days=1)


@pytest.mark.parametrize("text", ["春节", "国庆", "清明", "五一", "端午", "中秋", "元旦"])
def test_first_working_day_after_holiday_uses_adjustments_not_weekday_only(text: str) -> None:
    names = {
        "春节": "春节",
        "国庆": "国庆节",
        "清明": "清明节",
        "五一": "劳动节",
        "端午": "端午节",
        "中秋": "中秋节",
        "元旦": "元旦",
    }
    anchor = next(day for day, name in statutory_dates(2026) if name == names[text])
    window = holiday_window(anchor)
    expected = window[1] + timedelta(days=1)
    while day_status(expected).is_off:
        expected += timedelta(days=1)
    result = parse_time_range("2026年" + text + "之后第一个工作日", BASE)
    assert not result.needs_clarification and local_date(result.start) == expected


@pytest.mark.parametrize(
    "text,year,month,day",
    [
        ("农历2026年正月初一", 2026, 1, 1),
        ("农历2025年闰六月初一", 2025, -6, 1),
        ("农历2025年腊月二十三", 2025, 12, 23),
        ("2026年农历八月十五", 2026, 8, 15),
        ("2026年农历五月初五", 2026, 5, 5),
        ("2026年农历正月十五", 2026, 1, 15),
    ],
)
def test_lunar_leap_and_twelfth_month_dates_match_pinned_calendar(text: str, year: int, month: int, day: int) -> None:
    solar = Lunar.fromYmd(year, month, day).getSolar()
    expected = date(solar.getYear(), solar.getMonth(), solar.getDay())
    result = parse_time_range(text, BASE)
    assert not result.needs_clarification and local_date(result.start) == expected


@pytest.mark.parametrize(
    "name,expected",
    [("立冬", date(2026, 11, 7)), ("冬至", date(2026, 12, 22)), ("立春", date(2026, 2, 4)), ("清明", date(2026, 4, 5))],
)
def test_solar_term_day_uses_the_requested_gregorian_year(name: str, expected: date) -> None:
    result = parse_time_range("2026年" + name + "那天", BASE)
    assert not result.needs_clarification and local_date(result.start) == expected
    # Independent library assertion uses the exact day, avoiding its June-table cross-year key ambiguity.
    assert name in Solar.fromYmd(expected.year, expected.month, expected.day).getLunar().getJieQi()


@pytest.mark.parametrize("text", ["2027年国庆之后第一个工作日", "2027年春节期间"])
def test_unpublished_arrangements_cannot_be_claimed_as_known_leave(text: str) -> None:
    result = parse_time_range(text, BASE)
    assert result.needs_clarification and result.confidence < 0.8


def test_absolutize_replaces_only_the_time_span_preserves_original_and_is_idempotent() -> None:
    text = "我下周三面试，记得带上作品集。"
    result = absolutize(text, BASE)
    assert result.original_text == text and result.text == "我2026-10-21（周三）面试，记得带上作品集。"
    assert result.replaced
    again = absolutize(result.text, BASE)
    assert again.text == result.text


@pytest.mark.parametrize("zone", ["UTC", "Asia/Tokyo", "America/New_York", "Pacific/Honolulu"])
def test_os_timezone_environment_does_not_change_explicit_owner_results(
    monkeypatch: pytest.MonkeyPatch, zone: str
) -> None:
    expected = parse_time_range("下周三下午三点", BASE).as_dict()
    previous = os.environ.get("TZ")
    try:
        monkeypatch.setenv("TZ", zone)
        if hasattr(time, "tzset"):
            time.tzset()
        assert parse_time_range("下周三下午三点", BASE.astimezone(ZoneInfo(zone))).as_dict() == expected
        assert os.environ["TZ"] == zone
    finally:
        if previous is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", previous)
        if hasattr(time, "tzset"):
            time.tzset()


def test_500_random_relative_dates_are_translation_equivariant_and_json_safe() -> None:
    rng = random.Random(2026102104)
    for _ in range(500):
        reference = datetime(2020, 1, 1, 11, 35, tzinfo=ZONE) + timedelta(days=rng.randrange(3650))
        offset = rng.randrange(-3, 4)
        word = {0: "今天", 1: "明天", 2: "后天", 3: "大后天", -1: "昨天", -2: "前天", -3: "大前天"}[offset]
        result = parse_time_range(word, reference)
        assert local_date(result.start) == reference.date() + timedelta(days=offset)
        assert result.end - result.start == timedelta(days=1)
        assert json.loads(json.dumps(result.as_dict()))["kind"] == "point"


@pytest.mark.parametrize("reference", [datetime(2026, 10, 17), None, "2026-10-17"])
def test_naive_or_non_datetime_reference_is_rejected(reference: object) -> None:
    with pytest.raises(ValueError):
        parse_time_range("明天", reference)


def test_reference_instant_at_owner_midnight_does_not_use_reference_zone_date() -> None:
    ref = datetime(2026, 10, 16, 16, 5, tzinfo=UTC)
    assert local_date(parse_time_range("今天", ref).start) == date(2026, 10, 17)

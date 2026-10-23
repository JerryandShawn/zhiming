"""P2 parity, unpublished arrangements, and independent physical-term/year checks."""

import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from lunar_python import Lunar, Solar

from mingjing_core.timekit import calendar_cn
from mingjing_core.timekit.almanac import almanac
from mingjing_core.timeparse.calendar_expressions import parse_calendar
from mingjing_core.timeparse.calendar_port import P2CalendarPort
from mingjing_core.timeparse.contracts import ParseContext

ZONE = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 10, 17, 12, tzinfo=ZONE)
NAMES = [
    ("元旦", "元旦"),
    ("春节", "春节"),
    ("清明", "清明节"),
    ("五一", "劳动节"),
    ("端午", "端午节"),
    ("中秋", "中秋节"),
    ("国庆", "国庆节"),
]


def parse(text: str, ref: datetime = NOW, calendar: object = None):
    return parse_calendar(text, ParseContext(ref, text=text), calendar)


def civil(value: datetime) -> date:
    return value.astimezone(ZONE).date()


@pytest.mark.parametrize("year", [2024, 2025, 2026])
@pytest.mark.parametrize("label,name", NAMES)
def test_explicit_festival_is_its_p2_statutory_day_not_invented_leave(year: int, label: str, name: str) -> None:
    expected = dict((name, day) for day, name in calendar_cn.statutory_dates(year))[name]
    result = parse(f"{year}年{label}")
    assert not result.needs_clarification and civil(result.start) == expected
    assert civil(result.end) == expected + timedelta(days=1)
    assert result.kind == "point" and result.original_text == f"{year}年{label}"


@pytest.mark.parametrize("label,name", NAMES)
def test_published_leave_window_matches_p2_and_first_workday_counts_makeup(label: str, name: str) -> None:
    festival = dict((name, day) for day, name in calendar_cn.statutory_dates(2026))[name]
    window = calendar_cn.holiday_window(festival)
    assert window is not None
    during = parse(f"2026年{label}期间")
    assert civil(during.start) == window[0] and civil(during.end) == window[1] + timedelta(days=1)
    after = window[1] + timedelta(days=1)
    while calendar_cn.day_status(after).is_off:
        after += timedelta(days=1)
    result = parse(f"2026年{label}之后第一个工作日")
    assert not result.needs_clarification and civil(result.start) == after


@pytest.mark.parametrize("label,_name", NAMES)
def test_2027_arrangement_is_unknown_even_though_statutory_day_is_known(label: str, _name: str) -> None:
    during = parse(f"2027年{label}期间")
    after = parse(f"2027年{label}之后第一个工作日")
    point = parse(f"2027年{label}")
    assert during.needs_clarification and during.reason == "holiday_arrangement_unpublished"
    assert after.needs_clarification and after.reason == "holiday_arrangement_unpublished"
    assert not point.needs_clarification and point.start is not None


def test_injected_synthetic_override_includes_a_weekend_makeup_day(tmp_path) -> None:
    synthetic = {
        "year": 2027,
        "papers": ["synthetic-test-only"],
        "days": [
            {"name": "国庆节", "date": "2027-10-01", "isOffDay": True},
            {"name": "国庆节", "date": "2027-10-02", "isOffDay": False},
        ],
    }
    (tmp_path / "2027.json").write_text(json.dumps(synthetic), encoding="utf-8")
    result = parse("2027年国庆之后第一个工作日", calendar=P2CalendarPort(directory=tmp_path))
    assert not result.needs_clarification
    assert civil(result.start) == date(2027, 10, 2) and civil(result.start).weekday() == 5


@pytest.mark.parametrize("label", ["春节", "国庆", "五一", "端午", "中秋", "清明", "元旦"])
@pytest.mark.parametrize("direction", ["前", "后", "前后"])
def test_fuzzy_festival_horizons_are_choices_not_seven_day_facts(label: str, direction: str) -> None:
    result = parse("2026年" + label + direction)
    assert result.start is None and result.end is None
    assert result.needs_clarification and len(result.candidates) >= 2 and result.confidence <= 0.5
    assert all(candidate.start is not None and candidate.end > candidate.start for candidate in result.candidates)


@pytest.mark.parametrize("word", ["年前", "年后"])
def test_unqualified_new_year_distinguishes_gregorian_from_spring_festival(word: str) -> None:
    result = parse(word)
    assert result.needs_clarification and len(result.candidates) == 2
    assert {candidate.label for candidate in result.candidates} == {"公历年界", "春节年界"}


@pytest.mark.parametrize(
    "ref",
    [
        datetime(2026, 1, 1, 12, tzinfo=ZONE),
        datetime(2026, 2, 16, 12, tzinfo=ZONE),
        NOW,
        datetime(2025, 7, 24, 12, tzinfo=ZONE),
    ],
)
def test_unqualified_lunar_date_searches_adjacent_lunar_years_without_host_timezone(ref: datetime) -> None:
    result = parse("腊月二十三", ref)
    assert not result.needs_clarification
    expected = []
    for year in range(ref.year - 1, ref.year + 2):
        value = Lunar.fromYmd(year, 12, 23).getSolar()
        expected.append(date(value.getYear(), value.getMonth(), value.getDay()))
    assert civil(result.start) == min(day for day in expected if day >= ref.date())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2025年闰六月初一", date(2025, 7, 25)),
        ("农历2026年正月初一", date(2026, 2, 17)),
        ("二〇二六年腊月二十三", date(2027, 1, 30)),
        ("2026年农历冬月二十", date(2026, 12, 28)),
    ],
)
def test_lunar_year_and_leap_month_round_trip_preserves_exact_lunar_identity(text: str, expected: date) -> None:
    result = parse(text)
    assert not result.needs_clarification and civil(result.start) == expected
    got = Solar.fromYmd(expected.year, expected.month, expected.day).getLunar()
    assert got.getMonth() < 0 if "闰" in text else got.getMonth() > 0


@pytest.mark.parametrize(
    "year,month,day,leap",
    [
        (2026, 6, 1, True),
        (2025, 5, 1, True),
        (2026, 0, 1, False),
        (2026, 13, 1, False),
        (2026, 1, 0, False),
        (2026, 1, 31, False),
        (2026, True, 1, False),
        (2026, 1, True, False),
        (2026, 1, 1, "yes"),
        (True, 1, 1, False),
        (1800, 1, 1, False),
    ],
)
def test_invalid_lunar_dates_are_rejected_not_rollover(year: int, month: int, day: int, leap: bool) -> None:
    with pytest.raises(ValueError):
        P2CalendarPort().lunar_date(year, month, day, leap)


@pytest.mark.parametrize("text", ["2026年闰六月初一", "农历十三月初一", "农历正月三十一", "农历1月123", "腊月123"])
def test_invalid_lunar_text_never_promotes_a_partial_day_to_confident_point(text: str) -> None:
    result = parse(text)
    assert result.needs_clarification and result.start is None


@pytest.mark.parametrize("name,month,day", [("立春", 2, 6), ("清明", 4, 7), ("立冬", 11, 10), ("冬至", 12, 25)])
@pytest.mark.parametrize("year", [2024, 2025, 2026])
def test_solar_term_matches_independent_p2_prev_next_at_later_civil_day(
    name: str, month: int, day: int, year: int
) -> None:
    oracle = almanac(datetime(year, month, day, 12, tzinfo=ZONE))
    assert oracle.jieqi["current"] == name
    actual = P2CalendarPort().solar_term(year, name)
    assert actual == datetime.fromisoformat(oracle.jieqi["current_at"])
    assert actual.year == year


def test_2026_winter_solstice_is_december22_not_the_table_previous_year_entry() -> None:
    result = parse("2026年冬至那天")
    assert civil(result.start) == date(2026, 12, 22)
    assert civil(parse("立冬那天").start) == date(2026, 11, 7)
    vague = parse("冬至前")
    assert vague.needs_clarification and vague.reason == "unspecified_horizon"


@pytest.mark.parametrize("zone", ["UTC", "Asia/Shanghai", "Asia/Tokyo", "America/New_York"])
def test_all_24_term_instants_are_zone_invariant_and_in_requested_year(zone: str) -> None:
    port = P2CalendarPort()
    for name in Lunar.JIE_QI:
        actual = port.solar_term(2026, name, zone)
        baseline = port.solar_term(2026, name)
        assert actual.astimezone(UTC) == baseline.astimezone(UTC) and baseline.year == 2026


@pytest.mark.parametrize(
    "text",
    [
        "没有时间表达",
        "记下我的偏好",
        "三年前住在杭州",
        "一年前的旧事",
        "十年后再说",
        "去年前后",
        "农历是什么",
        "量子物理",
        "六月十二号",
        "三月八日",
        "购买十月期货",
        "春天去散步",
    ],
)
def test_non_calendar_or_unmarked_gregorian_text_is_not_fabricated(text: str) -> None:
    result = parse(text)
    assert result is None or result.needs_clarification


def test_missing_calendar_services_fail_closed_with_no_foreign_error_contents() -> None:
    result = parse("2026年国庆期间", calendar=object())
    assert result.needs_clarification and result.reason == "calendar_unavailable"


@pytest.mark.parametrize("ref", [datetime(2025, 7, 24, 12, tzinfo=ZONE), datetime(2026, 2, 16, 12, tzinfo=ZONE), NOW])
def test_lunar_monthly_cycle_includes_actual_leap_month_and_keeps_rule(ref: datetime) -> None:
    result = parse("每月初一", ref)
    assert not result.needs_clarification and result.kind == "recurring"
    assert result.recurrence == "lunar_monthly:day=1;include_leap=true"
    lunar = Solar.fromYmd(*civil(result.start).timetuple()[:3]).getLunar()
    assert lunar.getDay() == 1 and civil(result.start) >= ref.date()
    if ref.year == 2025:
        assert lunar.getMonth() == -6 and civil(result.start) == date(2025, 7, 25)


def test_annual_lunar_cycle_preserves_the_lunar_month_and_day() -> None:
    result = parse("每年农历八月十五")
    assert result.kind == "recurring" and result.recurrence == "lunar_yearly:month=8;day=15;leap=false"
    lunar = Solar.fromYmd(*civil(result.start).timetuple()[:3]).getLunar()
    assert (lunar.getMonth(), lunar.getDay()) == (8, 15)

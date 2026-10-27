"""Synthetic scoped-profile dates: independent civil truth, provenance, customs and clocks."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.timeparse.calendar_port import P2CalendarPort
from mingjing_core.timeparse.extended_v2 import absolutize_extended
from mingjing_core.timeparse.profile_contracts_v2 import InMemoryProfileDates, ProfileDateRecord, ProfileScope
from mingjing_core.timeparse.profile_dates_v2 import parse_profile_date

ZONE = ZoneInfo("Asia/Shanghai")
SCOPE = ProfileScope("synthetic-owner", "synthetic-self")
BASE = datetime(2026, 10, 17, 12, tzinfo=ZONE)


def record(key="birthday", month=12, day=3, **kwargs):
    return ProfileDateRecord(SCOPE, key, month, day, "synthetic-source-private", confirmed=True, **kwargs)


def parse(text, item=None, ref=BASE, tz="Asia/Shanghai"):
    return parse_profile_date(text, ref, tz, scope=SCOPE, profiles=InMemoryProfileDates((item or record(),)))


def local_day(result, tz="Asia/Shanghai"):
    return result.start.astimezone(ZoneInfo(tz)).date()


def assert_day(result, expected):
    assert not result.needs_clarification
    assert local_day(result) == expected
    assert result.end == datetime.combine(expected + timedelta(days=1), time(), ZONE).astimezone(UTC)
    assert result.original_text[result.span[0] : result.span[1]] == result.matched_text


YEAR_CASES = [
    (f"{prefix}我的生日", month, date(year, month, 8))
    for month in range(1, 13)
    for prefix, year in (("今年", 2026), ("明年", 2027), ("去年", 2025), ("2028年", 2028))
]
SAME_DAY_CASES = [
    (text, month, date(2027 if strict else 2026, month, 17))
    for month in range(1, 13)
    for text, strict in (("生日那天", False), ("我的生日", False), ("下个生日", True))
]
OFFSET_CASES = [
    (f"今年生日{suffix}", month, date(2026, month, 15) + timedelta(days=delta))
    for month in range(1, 13)
    for suffix, delta in (("提前三天", -3), ("前两天", -2), ("三天后", 3), ("之后10天", 10))
]


@pytest.mark.parametrize("text,month,expected", YEAR_CASES)
def test_explicit_gregorian_occurrence_years(text, month, expected):
    assert_day(parse(text, record(month=month, day=8)), expected)


@pytest.mark.parametrize("text,month,expected", SAME_DAY_CASES)
def test_same_day_is_inclusive_unless_explicitly_next(text, month, expected):
    ref = datetime(2026, month, 17, 23, 59, tzinfo=ZONE)
    assert_day(parse(text, record(month=month, day=17), ref), expected)


@pytest.mark.parametrize("text,month,expected", OFFSET_CASES)
def test_offsets_use_chosen_anchor_and_can_cross_month_or_year(text, month, expected):
    assert_day(parse(text, record(month=month, day=15)), expected)


@pytest.mark.parametrize("key,label", [("wedding_anniversary", "结婚"), ("employment_anniversary", "入职")])
@pytest.mark.parametrize("count,number", [(0, "零"), (1, "一"), (2, "两"), (5, "五"), (10, "十"), (100, "一百")])
def test_anniversary_count_is_anchored_to_confirmed_original_year(key, label, count, number):
    item = record(key, month=6, day=2, year=2020)
    assert_day(parse(f"距离{label}{number}周年还有多久", item), date(2020 + count, 6, 2))


@pytest.mark.parametrize("text", ["搬家纪念日", "我的搬家纪念日", "今年搬家纪念日", "“搬家”纪念日"])
def test_custom_anniversary_key_is_explicit(text):
    result = parse(text, record("custom:搬家", 12, 3))
    assert_day(result, date(2026, 12, 3))
    assert "synthetic-source-private" not in repr(result.as_dict())


@pytest.mark.parametrize("text", ["三年后我的生日", "两年后我的生日", "my birthday", "next birthday"])
def test_relative_year_and_english_profile_anchors(text):
    year = 2029 if text.startswith("三") else 2028 if text.startswith("两") else 2026
    assert_day(parse(text), date(year, 12, 3))


@pytest.mark.parametrize("count", [1, 3, 5])
def test_years_after_wedding_is_relative_to_the_original_event(count):
    assert_day(parse(f"结婚{count}年后", record("wedding_anniversary", 5, 6, year=2020)), date(2020 + count, 5, 6))


@pytest.mark.parametrize(
    "text,month,day,expected",
    [
        ("2026年生日", 1, 1, date(2026, 2, 17)),
        ("2026年生日", 12, 23, date(2026, 2, 10)),
        ("2025年生日", 6, 1, date(2025, 6, 25)),
        ("2026年生日", 8, 15, date(2026, 9, 25)),
    ],
)
def test_lunar_date_selects_the_occurrence_in_the_stated_gregorian_year(text, month, day, expected):
    assert_day(parse(text, record(month=month, day=day, calendar_kind="lunar")), expected)


def test_existing_lunar_leap_month_is_resolved_without_fabricating_regular_month_policy():
    item = record(month=6, day=1, calendar_kind="lunar", leap_month=True)
    assert_day(parse("生日那天", item, datetime(2025, 7, 20, tzinfo=ZONE)), date(2025, 7, 25))


@pytest.mark.parametrize("year", [2025, 2026, 2027, 2029, 2100])
def test_non_leap_year_february29_has_two_unselected_custom_candidates(year):
    result = parse(f"{year}年生日", record(month=2, day=29))
    assert result.start is None and result.end is None and result.needs_clarification
    assert result.reason == "leap_day_policy"
    assert {local_day(item) for item in result.candidates} == {date(year, 2, 28), date(year, 3, 1)}


def test_absent_lunar_leap_month_is_not_silently_converted_to_regular_month():
    item = record(month=6, day=1, calendar_kind="lunar", leap_month=True)
    result = parse("2026年生日", item)
    assert result.start is None and result.needs_clarification and result.reason == "leap_month_policy"
    assert any(local_day(choice).year > 2026 for choice in result.candidates)


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": ProfileScope("other", "synthetic-self")},
        {"scope": ProfileScope("synthetic-owner", "other")},
        {"key": "custom:wrong"},
        {"active": False},
        {"current": False},
        {"confirmed": False},
        {"revoked": True},
        {"incognito": True},
        {"current_revision": 2},
    ],
)
def test_parser_filters_a_hostile_projection_itself(changes):
    class HostilePort:
        def lookup(self, scope, key):
            return (replace(record(), **changes),)

    result = parse_profile_date("我的生日", BASE, scope=SCOPE, profiles=HostilePort())
    assert result.needs_clarification and result.start is None and not result.candidates


@pytest.mark.parametrize(
    "text",
    [
        "我妈妈的生日",
        "同事的生日",
        "his birthday",
        "her birthday",
        "their birthday",
        "小明的生日",
        "John's birthday",
        "my mother's birthday",
        "我前任的生日",
        "妻子生日",
    ],
)
def test_unbound_third_party_subject_never_looks_up_the_current_profile(text):
    class ForbiddenLookup:
        def lookup(self, scope, key):
            raise AssertionError("must not query")

    result = parse_profile_date(text, BASE, scope=SCOPE, profiles=ForbiddenLookup())
    assert result.start is None and not result.candidates and result.needs_clarification
    assert result.reason == "profile_subject_or_key_unclear"


@pytest.mark.parametrize(
    "text",
    ["birthday and wedding anniversary", "今年生日还是明年生日", "我的生日和结婚纪念日", "我的生日和搬家纪念日"],
)
def test_multiple_profile_dates_never_automatically_select_one(text):
    result = parse(text)
    assert result.start is None and result.needs_clarification


@pytest.mark.parametrize("text", ["随便聊聊", "tomorrow", "今天", "明年十一月", "every Monday"])
def test_non_profile_text_never_queries_profiles(text):
    class ForbiddenLookup:
        def lookup(self, scope, key):
            raise AssertionError("must not query")

    assert parse_profile_date(text, BASE, scope=SCOPE, profiles=ForbiddenLookup()) is None


def test_profile_error_messages_do_not_expose_provider_private_details():
    class PortError(Exception):
        pass

    class FailingPort:
        def lookup(self, scope, key):
            raise PortError("synthetic private profile body and disk path")

    result = parse_profile_date("我的生日", BASE, scope=SCOPE, profiles=FailingPort())
    assert result.reason == "profile_port_unavailable"
    assert "synthetic private" not in repr(result.as_dict())


def test_conflicting_sources_and_missing_origin_year_are_not_resolved_by_guessing():
    records = (record(), replace(record(), day=4, source_id="second-private"))
    result = parse_profile_date("我的生日", BASE, scope=SCOPE, profiles=InMemoryProfileDates(records))
    assert result.start is None and not result.candidates and result.needs_clarification
    anniversary = parse("结婚五周年", record("wedding_anniversary"))
    assert anniversary.reason == "missing_profile_origin_year" and anniversary.start is None


def test_quoted_custom_names_are_not_silently_changed_by_pronouns_inside_the_name():
    assert_day(parse("“我的搬家”纪念日", record("custom:我的搬家")), date(2026, 12, 3))


def test_profile_port_and_calendar_are_injected_and_no_automatic_real_profile_access_exists():
    result = parse_profile_date("我的生日", BASE)
    assert result.reason == "missing_profile_context" and result.start is None
    item = record(month=1, day=1, calendar_kind="lunar")
    result = parse_profile_date(
        "今年生日",
        BASE,
        scope=SCOPE,
        profiles=InMemoryProfileDates((item,)),
        calendar=P2CalendarPort(),
    )
    assert_day(result, date(2026, 2, 17))


@pytest.mark.parametrize(
    "text",
    [
        "每年生日",
        "每月生日",
        "每周我的生日",
        "每年的生日",
        "每年结婚纪念日",
        "每月入职纪念日",
        "每年搬家纪念日",
        "every year my birthday",
        "each year wedding anniversary",
        "my birthday every year",
        "anniversary each month",
        "every week anniversary",
    ],
)
@pytest.mark.parametrize("scoped", [False, True])
def test_profile_recurrence_never_becomes_one_off_event_even_with_confirmed_profile(text, scoped):
    records = tuple(record(key) for key in ("birthday", "wedding_anniversary", "employment_anniversary", "custom:搬家"))
    kwargs = {"scope": SCOPE, "profiles": InMemoryProfileDates(records)} if scoped else {}
    result = parse_profile_date(text, BASE, **kwargs)
    assert result.kind == "recurring" and result.needs_clarification and result.recurrence is None
    assert result.start is None and result.end is None
    assert text[result.span[0] : result.span[1]] == result.matched_text
    if not scoped:
        assert not result.candidates
    absolute = absolutize_extended(
        text,
        BASE,
        profile_scope=SCOPE if scoped else None,
        profiles=kwargs.get("profiles"),
    )
    assert absolute.result.kind == "recurring" and absolute.result.needs_clarification
    assert not absolute.replaced and absolute.text == text


def test_a_quoted_custom_name_containing_cycle_words_is_still_a_literal_profile_key():
    assert_day(parse("“每年搬家”纪念日", record("custom:每年搬家")), date(2026, 12, 3))


@pytest.mark.parametrize("seed", range(1000))
def test_frozen_clock_random_civil_dates_are_timezone_explicit_and_same_instant_stable(seed):
    rng = random.Random(seed)
    tz = rng.choice(("Asia/Shanghai", "Asia/Tokyo", "America/Los_Angeles", "UTC"))
    local_ref = datetime(rng.randrange(2020, 2041), rng.randrange(1, 13), rng.randrange(1, 29), 12, tzinfo=ZoneInfo(tz))
    clock = FrozenClock(local_ref)
    item = record(month=rng.randrange(1, 13), day=rng.randrange(1, 29))
    expected = date(local_ref.year, item.month, item.day)
    if expected < local_ref.date():
        expected = date(local_ref.year + 1, item.month, item.day)
    first = parse("我的生日", item, clock.now(), tz)
    second = parse("我的生日", item, clock.now().astimezone(ZoneInfo("Asia/Tokyo")), tz)
    assert first == second and local_day(first, tz) == expected
    assert first.start == datetime.combine(expected, time(), ZoneInfo(tz)).astimezone(UTC)
    assert first.end > first.start and first.confidence == 0.95

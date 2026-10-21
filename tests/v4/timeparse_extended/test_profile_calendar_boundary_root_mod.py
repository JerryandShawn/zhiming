"""Independent observance policies and hostile calendar projections; mappings are synthetic only."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timeparse.profile_calendar_v2 import anniversary_occurrence, occurrence_in_year
from mingjing_core.timeparse.profile_contracts_v2 import InMemoryProfileDates, ProfileDateRecord, ProfileScope
from mingjing_core.timeparse.profile_dates_v2 import parse_profile_date

SCOPE = ProfileScope("synthetic-root-calendar-owner", "synthetic-root-calendar-self")
REF = datetime(2026, 10, 17, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
PRIVATE = "synthetic provider exception body C:/private/not-a-real-file"


def record(**changes: Any) -> ProfileDateRecord:
    values = dict(scope=SCOPE, key="birthday", month=4, day=30, source_id="synthetic-only", confirmed=True)
    return ProfileDateRecord(**(values | changes))


@dataclass
class SyntheticCalendar:
    """Only a boundary-test port; these dates assert no Chinese-calendar accuracy."""

    mapping: dict[tuple[int, int, int, bool], Any] = field(default_factory=dict)
    calls: list[tuple[int, int, int, bool]] = field(default_factory=list)

    def lunar_date(self, year: int, month: int, day: int, leap: bool = False) -> date:
        key = year, month, day, leap
        self.calls.append(key)
        value = self.mapping.get(key, ValueError(PRIVATE))
        if isinstance(value, Exception):
            raise value
        return value


def parse(item: ProfileDateRecord, calendar: SyntheticCalendar, text: str = "2026年生日") -> Any:
    return parse_profile_date(text, REF, scope=SCOPE, profiles=InMemoryProfileDates((item,)), calendar=calendar)


def candidate_days(value: Any) -> set[date]:
    return {row.start.astimezone(ZoneInfo("Asia/Shanghai")).date() for row in value.candidates}


@pytest.mark.parametrize("year", [1, 1899, 1900, 2201, 9998, 9999])
def test_lunar_outside_supported_occurrence_year_never_queries_provider(year: int) -> None:
    calendar = SyntheticCalendar()
    value = occurrence_in_year(record(calendar_kind="lunar"), year, calendar)
    assert value.days == () and value.nominal is None and value.reason == "profile_calendar_unavailable"
    assert calendar.calls == []


@pytest.mark.parametrize("year", [1901, 2026, 2200])
def test_lunar_twelfth_month_in_january_uses_previous_lunar_year(year: int) -> None:
    expected = date(year, 1, 15)
    calendar = SyntheticCalendar({(year - 1, 12, 23, False): expected})
    value = occurrence_in_year(record(month=12, day=23, calendar_kind="lunar"), year, calendar)
    assert value.days == (expected,) and value.nominal == expected and value.reason is None
    assert all(1900 <= call[0] <= 2200 for call in calendar.calls)


def test_two_distinct_current_year_occurrences_are_both_candidates_never_first_wins() -> None:
    calendar = SyntheticCalendar({(2025, 4, 8, False): date(2026, 1, 3), (2026, 4, 8, False): date(2026, 12, 3)})
    value = parse(record(day=8, calendar_kind="lunar"), calendar)
    assert value.start is None and value.needs_clarification and value.reason == "profile_calendar_ambiguous"
    assert candidate_days(value) == {date(2026, 1, 3), date(2026, 12, 3)}


def test_duplicate_mapping_same_civil_day_does_not_create_fake_ambiguity() -> None:
    expected = date(2026, 6, 3)
    calendar = SyntheticCalendar({(2025, 4, 8, False): expected, (2026, 4, 8, False): expected})
    value = parse(record(day=8, calendar_kind="lunar"), calendar)
    assert not value.needs_clarification and value.reason == "confirmed_profile_date"
    assert value.start.astimezone(ZoneInfo("Asia/Shanghai")).date() == expected


def test_short_month_thirtieth_proposes_last_day_and_next_day_without_choosing_custom() -> None:
    calendar = SyntheticCalendar({(2026, 4, 29, False): date(2026, 6, 14)})
    value = parse(record(calendar_kind="lunar"), calendar)
    assert value.start is None and value.needs_clarification and value.reason == "lunar_short_month_policy"
    assert candidate_days(value) == {date(2026, 6, 14), date(2026, 6, 15)}


@pytest.mark.parametrize("day", [1, 8, 29])
def test_missing_non_thirtieth_is_unavailable_not_an_invented_short_month_custom(day: int) -> None:
    calendar = SyntheticCalendar()
    value = parse(record(day=day, calendar_kind="lunar"), calendar)
    assert value.start is None and value.needs_clarification and value.reason == "profile_calendar_unavailable"
    assert not value.candidates and all(call[2] == day for call in calendar.calls)


def test_short_month_without_a_last_day_returns_no_invented_candidates() -> None:
    value = parse(record(calendar_kind="lunar"), SyntheticCalendar())
    assert value.start is None and value.needs_clarification and not value.candidates
    assert value.reason == "lunar_short_month_policy"


def test_absent_leap_month_offers_regular_and_later_leap_as_separate_customs() -> None:
    calendar = SyntheticCalendar({(2026, 4, 8, False): date(2026, 6, 3), (2029, 4, 8, True): date(2029, 7, 3)})
    value = parse(record(day=8, calendar_kind="lunar", leap_month=True), calendar)
    assert value.start is None and value.needs_clarification and value.reason == "leap_month_policy"
    assert candidate_days(value) == {date(2026, 6, 3), date(2029, 7, 3)}


def test_absent_leap_and_regular_month_cannot_fabricate_a_date() -> None:
    calendar = SyntheticCalendar()
    value = parse(record(day=8, calendar_kind="lunar", leap_month=True), calendar)
    assert value.start is None and value.needs_clarification and value.reason == "leap_month_policy"
    assert not value.candidates and all(1900 <= call[0] <= 2200 for call in calendar.calls)


@pytest.mark.parametrize("bad", [None, "2026-06-03", datetime(2026, 6, 3), RuntimeError(PRIVATE)])
@pytest.mark.parametrize("phase", ["exact", "short_month", "leap_search"])
def test_malformed_calendar_outputs_and_errors_fail_closed_without_provider_details(bad: Any, phase: str) -> None:
    leap = phase == "leap_search"
    item = record(day=30 if phase == "short_month" else 8, calendar_kind="lunar", leap_month=leap)
    key = (2026, 4, 29, False) if phase == "short_month" else (2029 if leap else 2026, 4, 8, leap)
    value = parse(item, SyntheticCalendar({key: bad}))
    assert value.start is None and value.needs_clarification and not value.candidates
    assert value.reason == "profile_calendar_unavailable" and PRIVATE not in repr(value.as_dict())


@pytest.mark.parametrize("leap", [False, True])
def test_anniversary_requires_original_year_and_never_queries_when_missing(leap: bool) -> None:
    calendar = SyntheticCalendar()
    item = record(day=8, calendar_kind="lunar", leap_month=leap)
    value = anniversary_occurrence(item, 5, calendar)
    assert value.days == () and value.reason == "missing_profile_origin_year" and calendar.calls == []


@pytest.mark.parametrize("year,count", [(1899, 0), (2200, 1), (9999, 1)])
def test_anniversary_outside_calendar_bounds_never_queries_provider(year: int, count: int) -> None:
    calendar = SyntheticCalendar()
    value = anniversary_occurrence(record(day=8, year=year, calendar_kind="lunar"), count, calendar)
    assert value.days == () and value.reason == "profile_calendar_unavailable" and calendar.calls == []


@pytest.mark.parametrize("leap,reason", [(False, "lunar_short_month_policy"), (True, "leap_month_policy")])
def test_missing_exact_anniversary_is_not_replaced_by_another_observance(leap: bool, reason: str) -> None:
    value = anniversary_occurrence(record(year=2020, calendar_kind="lunar", leap_month=leap), 6, SyntheticCalendar())
    assert value.days == () and value.nominal is None and value.reason == reason


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": None},
        {"key": ""},
        {"source_id": " "},
        {"calendar_kind": "wrong"},
        {"active": 1},
        {"leap_month": "false"},
        {"month": True},
        {"day": True},
        {"year": True},
        {"year": 0},
        {"month": 0},
        {"month": 13},
        {"day": 31},
        {"revision": True},
        {"revision": 0},
        {"current_revision": 0},
        {"calendar_kind": "lunar", "day": 31},
        {"leap_month": True},
    ],
)
def test_untrusted_profile_projection_must_be_well_typed_before_parsing(changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        record(**changes)


@pytest.mark.parametrize("output", [None, {}, (record(),) * 101])
def test_malformed_or_oversized_profile_lookup_cannot_authorize_dates(output: Any) -> None:
    class UntrustedPort:
        def lookup(self, scope: ProfileScope, key: str) -> Any:
            return output

    value = parse_profile_date("我的生日", REF, scope=SCOPE, profiles=UntrustedPort())
    assert value.needs_clarification and value.reason == "profile_port_unavailable" and value.start is None

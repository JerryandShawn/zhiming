"""Calendar-only profile observances; ambiguous customs are returned, never silently chosen."""

from dataclasses import dataclass
from datetime import date, timedelta

from .calendar_port import CalendarPort
from .profile_contracts_v2 import ProfileDateRecord


@dataclass(frozen=True)
class ProfileOccurrence:
    days: tuple[date, ...] = ()
    reason: str | None = None
    nominal: date | None = None


def _solar(record: ProfileDateRecord, year: int) -> ProfileOccurrence:
    try:
        day = date(year, record.month, record.day)
        return ProfileOccurrence((day,), nominal=day)
    except ValueError:
        if record.month == 2 and record.day == 29:
            days = (date(year, 2, 28), date(year, 3, 1))
            return ProfileOccurrence(days, "leap_day_policy", days[-1])
        return ProfileOccurrence(reason="profile_calendar_unavailable")


def _convert(port: CalendarPort, record: ProfileDateRecord, year: int, leap: bool) -> date | None:
    try:
        day = port.lunar_date(year, record.month, record.day, leap)
    except ValueError:
        return None
    if type(day) is not date:
        raise ValueError("profile_calendar_result_invalid")
    return day


def _lunar_in_year(port: CalendarPort, record: ProfileDateRecord, year: int, leap: bool) -> tuple[date, ...]:
    result = []
    for lunar_year in (year - 1, year):
        if not 1900 <= lunar_year <= 2200:
            continue
        day = _convert(port, record, lunar_year, leap)
        if day is not None and day.year == year:
            result.append(day)
    return tuple(sorted(set(result)))


def _next_leap(port: CalendarPort, record: ProfileDateRecord, after: date) -> date | None:
    for year in range(max(1900, after.year - 1), min(2201, after.year + 21)):
        day = _convert(port, record, year, True)
        if day is not None and day > after:
            return day
    return None


def _lunar_short_month(port: CalendarPort, record: ProfileDateRecord, year: int) -> ProfileOccurrence:
    if record.day != 30:
        return ProfileOccurrence(reason="profile_calendar_unavailable")
    days = []
    for lunar_year in (year - 1, year):
        try:
            last_day = port.lunar_date(lunar_year, record.month, 29, record.leap_month)
        except ValueError:
            continue
        if type(last_day) is not date:
            raise ValueError("profile_calendar_result_invalid")
        if last_day.year == year:
            days.extend((last_day, last_day + timedelta(days=1)))
    unique = tuple(sorted(set(days)))
    return ProfileOccurrence(unique, "lunar_short_month_policy", max(unique) if unique else None)


def occurrence_in_year(record: ProfileDateRecord, year: int, port: CalendarPort) -> ProfileOccurrence:
    """year means Gregorian occurrence year, including lunar twelfth-month dates in January."""
    if not 1 <= year <= 9998:
        return ProfileOccurrence(reason="profile_calendar_unavailable")
    if record.calendar_kind == "solar":
        return _solar(record, year)
    if not 1901 <= year <= 2200:
        return ProfileOccurrence(reason="profile_calendar_unavailable")
    exact = _lunar_in_year(port, record, year, record.leap_month)
    if len(exact) == 1:
        return ProfileOccurrence(exact, nominal=exact[0])
    if len(exact) > 1:
        return ProfileOccurrence(exact, "profile_calendar_ambiguous", exact[-1])
    if not record.leap_month:
        return _lunar_short_month(port, record, year)
    regular = _lunar_in_year(port, record, year, False)
    nominal = regular[-1] if regular else date(year, 12, 31)
    following = _next_leap(port, record, nominal)
    choices = tuple(sorted(set((*regular, *((following,) if following else ())))))
    return ProfileOccurrence(choices, "leap_month_policy", nominal)


def anniversary_occurrence(record: ProfileDateRecord, count: int, port: CalendarPort) -> ProfileOccurrence:
    if record.year is None:
        return ProfileOccurrence(reason="missing_profile_origin_year")
    year = record.year + count
    if not 1 <= year <= 9998:
        return ProfileOccurrence(reason="profile_calendar_unavailable")
    if record.calendar_kind == "solar":
        return _solar(record, year)
    if not 1900 <= year <= 2200:
        return ProfileOccurrence(reason="profile_calendar_unavailable")
    day = _convert(port, record, year, record.leap_month)
    if day is not None:
        return ProfileOccurrence((day,), nominal=day)
    return ProfileOccurrence(reason="leap_month_policy" if record.leap_month else "lunar_short_month_policy")

"""Read-only P2 bridge: no holiday tables and no weekday fallback for unpublished years."""

from collections.abc import Iterator
from datetime import date

from mingjing_core.timeparse.calendar_port import CalendarPort

from .recurrence_contracts import RecurrenceError, RecurrenceRule


class CalendarUnavailable(RecurrenceError):
    """A dependency cannot establish an authoritative calendar occurrence."""


def day_allowed(day: date, rule: RecurrenceRule, calendar: CalendarPort) -> tuple[bool, str | None]:
    filter_name = rule.kind if rule.kind in {"workday", "offday"} else rule.day_filter
    if filter_name == "all":
        return True, "p2_lunar" if rule.kind.startswith("lunar_") else None
    try:
        status = calendar.day_status(day)
        if status.source == "unpublished":
            raise CalendarUnavailable("calendar_unpublished")
        if status.source not in {"builtin", "override"} or type(status.is_off) is not bool:
            raise CalendarUnavailable("calendar_status_invalid")
        if status.kind not in {"workday", "weekend", "holiday", "adjusted_workday"}:
            raise CalendarUnavailable("calendar_status_invalid")
        if status.is_off != (status.kind in {"weekend", "holiday"}):
            raise CalendarUnavailable("calendar_status_invalid")
        return status.is_off == (filter_name == "offday"), status.source
    except CalendarUnavailable:
        raise
    except (ValueError, LookupError, AttributeError, TypeError, OSError):
        raise CalendarUnavailable("calendar_unavailable") from None


def lunar_dates(rule: RecurrenceRule, start: date, calendar: CalendarPort) -> Iterator[date]:
    if not 1900 <= start.year <= 2200:
        raise CalendarUnavailable("lunar_calendar_year_outside_supported_range")
    for year in range(max(1900, start.year - 1), 2201):
        values = set()
        for month in range(1, 13) if rule.kind == "lunar_monthly" else (rule.month,):
            leaps = (False, True) if rule.kind == "lunar_monthly" and rule.include_leap else (rule.leap,)
            for leap in leaps:
                candidate = _lunar_date(calendar, year, month, rule.day, leap)
                if candidate is not None and candidate >= start:
                    values.add(candidate)
        yield from sorted(values)


def _lunar_date(calendar: CalendarPort, year: int, month: int, day: int, leap: bool) -> date | None:
    try:
        result = calendar.lunar_date(year, month, day, leap)
    except (ValueError, LookupError):
        return None
    except (AttributeError, TypeError, OSError):
        raise CalendarUnavailable("lunar_calendar_unavailable") from None
    if type(result) is not date:
        raise CalendarUnavailable("lunar_calendar_result_invalid")
    return result

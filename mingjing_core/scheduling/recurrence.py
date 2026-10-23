"""Pure next-occurrence calculation; never sends or claims a reminder."""

from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from mingjing_core.timeparse.calendar_port import CalendarPort, P2CalendarPort

from .recurrence_calendar import CalendarUnavailable, day_allowed, lunar_dates
from .recurrence_civil import civil_dates
from .recurrence_contracts import NextTriggerResult, RecurrenceError, RecurrenceRule, aware
from .recurrence_machine import parse_recurrence
from .recurrence_wall import resolve_wall

__all__ = ["next_trigger", "parse_recurrence"]


def next_trigger(
    rule: RecurrenceRule | str, after: datetime, calendar: CalendarPort | None = None, *, inclusive: bool = False
) -> NextTriggerResult:
    after = aware(after)
    if type(inclusive) is not bool:
        raise RecurrenceError("inclusive_flag_invalid")
    if isinstance(rule, str):
        rule = parse_recurrence(rule)
    if not isinstance(rule, RecurrenceRule):
        raise RecurrenceError("recurrence_rule_required")
    if rule.local_time is None:
        return NextTriggerResult(None, needs_clarification=True, reason="local_time_required")
    calendar = P2CalendarPort() if calendar is None else calendar
    start = after.astimezone(ZoneInfo(rule.time_zone)).date()
    dates = lunar_dates(rule, start, calendar) if rule.kind.startswith("lunar_") else civil_dates(rule, start)
    try:
        for day in dates:
            result = resolve_wall(day, rule, after, inclusive)
            if result is None:
                continue
            allowed, source = day_allowed(day, rule, calendar)
            if not allowed:
                continue
            return replace(result, calendar_source=source)
    except CalendarUnavailable as error:
        return NextTriggerResult(None, needs_clarification=True, reason=error.reason_code)
    return NextTriggerResult(None, needs_clarification=True, reason="search_horizon_exhausted")

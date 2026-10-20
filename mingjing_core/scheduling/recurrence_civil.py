"""Civil-day iteration skips absent month dates instead of clamping them."""

from collections.abc import Iterator
from datetime import date, timedelta

from .recurrence_contracts import RecurrenceRule


def civil_dates(rule: RecurrenceRule, start: date) -> Iterator[date]:
    if rule.kind in {"daily", "workday", "offday", "weekly"}:
        yield from _days(rule, start)
    elif rule.kind == "monthly":
        yield from _months(rule, start)
    else:
        yield from _years(rule, start)


def _days(rule: RecurrenceRule, start: date) -> Iterator[date]:
    offset = (rule.weekday - start.weekday()) % 7 if rule.kind == "weekly" else 0
    interval = 7 if rule.kind == "weekly" else 1
    for elapsed in range(offset, 3661, interval):
        try:
            yield start + timedelta(days=elapsed)
        except OverflowError:
            return


def _months(rule: RecurrenceRule, start: date) -> Iterator[date]:
    index = start.year * 12 + start.month - 1
    for offset in range(121):
        year, month = divmod(index + offset, 12)
        try:
            candidate = date(year, month + 1, rule.day)
        except ValueError:
            continue
        if candidate >= start:
            yield candidate


def _years(rule: RecurrenceRule, start: date) -> Iterator[date]:
    for year in range(start.year, min(9999, start.year + 10) + 1):
        try:
            candidate = date(year, rule.month, rule.day)
        except ValueError:
            continue
        if candidate >= start:
            yield candidate

"""Next lunar occurrence is computed locally; recurrence never assumes every month has day 30."""

import re
from datetime import date, timedelta

from .calendar_helpers import chinese_number, unknown
from .calendar_lunar import DAY, MONTH
from .calendar_port import CalendarPort
from .contracts import ParseContext, TimeRangeResult, make_result

MONTHLY = re.compile(rf"每(?:个)?(?P<calendar>农历|阴历)?月(?P<day>{DAY})(?:日|号)?")
YEARLY = re.compile(rf"每年(?:的)?(?P<calendar>农历|阴历)?(?P<leap>闰)?(?P<month>{MONTH})月(?P<day>{DAY})(?:日|号)?")


def _next_lunar(calendar: CalendarPort, ctx: ParseContext, day: int, month: int | None, leap: bool) -> date | None:
    horizon = 3 if month is None else 20 if leap else 3
    candidates = []
    for year in range(ctx.local_date.year - 1, ctx.local_date.year + horizon):
        months = range(1, 13) if month is None else (month,)
        for candidate_month in months:
            for candidate_leap in (False, True) if month is None else (leap,):
                try:
                    value = calendar.lunar_date(year, candidate_month, day, candidate_leap)
                    if value >= ctx.local_date:
                        candidates.append(value)
                except (ValueError, LookupError):
                    continue
    return min(candidates) if candidates else None


def parse_lunar_cycle(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    yearly = YEARLY.search(text)
    monthly = MONTHLY.search(text) if yearly is None else None
    match = yearly or monthly
    if match is None:
        return None
    marked = match["calendar"] or match["day"].startswith(("初", "廿"))
    if yearly is not None:
        marked = marked or match["leap"] or match["month"] in {"正", "冬", "腊"}
    if not marked:
        return None
    try:
        day = chinese_number(match["day"])
        month = chinese_number(match["month"]) if yearly is not None else None
        leap = bool(match["leap"]) if yearly is not None else False
        selected = _next_lunar(calendar, ctx, day, month, leap)
        if selected is None:
            return unknown(ctx, match.group(), "lunar_cycle_occurrence_unavailable")
        recurrence = (
            f"lunar_yearly:month={month};day={day};leap={str(leap).lower()}"
            if yearly is not None
            else f"lunar_monthly:day={day};include_leap=true"
        )
        return make_result(
            ctx,
            start=selected,
            end=selected + timedelta(days=1),
            matched_text=match.group(),
            kind="recurring",
            recurrence=recurrence,
            confidence=0.9,
        )
    except (ValueError, LookupError, AttributeError, TypeError, KeyError):
        return unknown(ctx, match.group(), "lunar_cycle_calendar_unavailable")

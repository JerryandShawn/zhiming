"""Solar terms use the P2 physical instant; vague before/after horizons remain questions."""

import re
from datetime import timedelta

from lunar_python import Lunar

from .calendar_helpers import YEAR_PATTERN, specified_year, unknown, vague_around
from .calendar_port import CalendarPort
from .contracts import ParseContext, TimeRangeResult, make_result

PATTERN = re.compile(
    YEAR_PATTERN + r"(?:节气)?(?P<term>" + "|".join(Lunar.JIE_QI) + r")"
    r"(?:的)?(?P<suffix>前后|之前|之后|前|后|那天|当天|时刻|交接时刻)?"
)


def parse_term(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    match = PATTERN.search(text)
    if match is None:
        return None
    try:
        year = specified_year(match["year"], ctx)
        years = (year,) if year is not None else (ctx.local_date.year, ctx.local_date.year + 1)
        instants = [calendar.solar_term(candidate, match["term"], ctx.tz) for candidate in years]
        instant = (
            instants[0] if year is not None else next(stamp for stamp in instants if stamp.date() >= ctx.local_date)
        )
        day, suffix = instant.astimezone(ctx.zone).date(), match["suffix"] or ""
        if suffix in {"前", "后", "前后", "之前", "之后"}:
            return vague_around(ctx, match.group(), day, suffix)
        if suffix in {"时刻", "交接时刻"}:
            return make_result(
                ctx,
                start=instant,
                end=instant,
                matched_text=match.group(),
                granularity="second",
                normalized_text=instant.isoformat(),
            )
        return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=match.group(), confidence=0.97)
    except (ValueError, LookupError, AttributeError, TypeError, StopIteration):
        return unknown(ctx, match.group(), "solar_term_unavailable")

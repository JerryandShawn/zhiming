"""Festival interpretation separates a fixed festival day from its published leave window."""

import re
from datetime import date, timedelta

from .calendar_helpers import YEAR_PATTERN, day_candidate, first_workday, specified_year, unknown, vague_around
from .calendar_port import CalendarPort
from .contracts import ParseContext, TimeRangeResult, make_result

NAMES = {
    "元旦": "元旦",
    "春节": "春节",
    "清明": "清明节",
    "清明节": "清明节",
    "五一": "劳动节",
    "劳动节": "劳动节",
    "端午": "端午节",
    "端午节": "端午节",
    "中秋": "中秋节",
    "中秋节": "中秋节",
    "国庆": "国庆节",
    "国庆节": "国庆节",
}
HOLIDAY_PATTERN = re.compile(
    YEAR_PATTERN + r"(?P<name>清明节|端午节|中秋节|国庆节|劳动节|元旦|春节|清明|五一|端午|中秋|国庆)"
    r"(?:的)?(?P<suffix>之?后(?:的)?第一个工作日|期间|前后|之前|之后|前|后|那天|当天)?"
)


def _festival_day(name: str, year: int | None, ctx: ParseContext, calendar: CalendarPort) -> date:
    years = (year,) if year is not None else (ctx.local_date.year, ctx.local_date.year + 1)
    dates = [day for candidate in years for day, label in calendar.statutory_dates(candidate) if label == NAMES[name]]
    if not dates:
        raise ValueError("法定节日日期不可用")
    return dates[0] if year is not None else next(day for day in dates if day >= ctx.local_date)


def parse_holiday(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    match = HOLIDAY_PATTERN.search(text)
    if match is None:
        return None
    raw, suffix = match.group(), match["suffix"] or ""
    try:
        day = _festival_day(match["name"], specified_year(match["year"], ctx), ctx, calendar)
        if suffix in {"前", "后", "前后", "之前", "之后"}:
            return vague_around(ctx, raw, day, suffix)
        if suffix == "期间" or "工作日" in suffix:
            return _published_window(raw, suffix, day, ctx, calendar)
        return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=raw)
    except (ValueError, LookupError, AttributeError, TypeError, StopIteration):
        return unknown(ctx, raw, "calendar_unavailable")


def _published_window(raw: str, suffix: str, day: date, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult:
    if calendar.day_status(day).source == "unpublished":
        return unknown(ctx, raw, "holiday_arrangement_unpublished", day=day)
    window = calendar.holiday_window(day)
    if window is None:
        return unknown(ctx, raw, "holiday_window_unavailable", day=day)
    if "工作日" in suffix:
        following = first_workday(calendar, window[1])
        if following is None:
            return unknown(ctx, raw, "workday_arrangement_unpublished")
        return make_result(ctx, start=following, end=following + timedelta(days=1), matched_text=raw)
    return make_result(
        ctx,
        start=window[0],
        end=window[1] + timedelta(days=1),
        matched_text=raw,
        kind="range",
        normalized_text=f"{window[0].isoformat()}至{window[1].isoformat()}（假期）",
    )


def parse_newyear(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    match = re.search(r"(?<![去今明后0-9零〇一二三四五六七八九十百千])年(?P<direction>前|后)(?!年)", text)
    if match is None:
        return None
    try:
        spring = _festival_day("春节", None, ctx, calendar)
        gregorian = date(ctx.local_date.year + 1, 1, 1)
        shift = -1 if match["direction"] == "前" else 0
        candidates = (
            day_candidate(gregorian + timedelta(days=shift), ctx, "公历年界"),
            day_candidate(spring + timedelta(days=shift), ctx, "春节年界"),
        )
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=match.group(),
            granularity="fuzzy",
            kind="range",
            confidence=0.3,
            normalized_text="公历年界或春节年界（待确认）",
            candidates=candidates,
            needs_clarification=True,
            reason="new_year_calendar_ambiguous",
        )
    except (ValueError, LookupError, AttributeError, TypeError, StopIteration):
        return unknown(ctx, match.group(), "calendar_unavailable")

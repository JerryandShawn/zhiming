"""Lunar dates retain year/leap-month uncertainty instead of silently normalizing invalid dates."""

import re
from datetime import date, timedelta

from .calendar_helpers import chinese_number, day_candidate, specified_year, unknown
from .calendar_port import CalendarPort
from .contracts import ParseContext, TimeRangeResult, make_result

YEAR = r"前年|去年|今年|明年|后年|[12]\d{3}|[一二][〇零一二三四五六七八九]{3}"
MONTH = r"正|冬|腊|[一二三四五六七八九十]{1,3}|\d{1,2}"
DAY = r"初[一二三四五六七八九十]{1,2}|[一二三四五六七八九十廿]{1,4}|\d{1,2}"
PATTERN = re.compile(
    rf"(?:(?P<year>{YEAR})年?)?(?P<marker>农历|阴历)?"
    rf"(?:(?P<year_after>{YEAR})年?)?(?P<leap>闰)?(?P<month>{MONTH})月(?P<day>{DAY})(?![一二三四五六七八九十廿\d])(?:日|号)?"
)


def _year_value(value: str | None, ctx: ParseContext) -> int | None:
    if not value:
        return None
    if value.endswith("年") or value in {"前年", "去年", "今年", "明年", "后年"}:
        return specified_year(value, ctx)
    return chinese_number(value)


def _dates(match: re.Match, ctx: ParseContext, calendar: CalendarPort) -> tuple[list[date], bool]:
    raw_year = match["year"] or match["year_after"]
    year = _year_value(raw_year, ctx)
    years = (year,) if year is not None else range(ctx.local_date.year - 1, ctx.local_date.year + 2)
    dates = []
    for candidate in years:
        try:
            dates.append(
                calendar.lunar_date(
                    candidate, chinese_number(match["month"]), chinese_number(match["day"]), bool(match["leap"])
                )
            )
        except (ValueError, LookupError):
            continue
    return sorted(dates), year is not None


def parse_lunar(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    for match in PATTERN.finditer(text):
        marked = match["marker"] or match["leap"] or match["month"] in {"正", "冬", "腊"}
        if not marked and not match["day"].startswith(("初", "廿")):
            continue
        try:
            dates, explicit_year = _dates(match, ctx, calendar)
            future = [day for day in dates if day >= ctx.local_date]
            selected = dates[0] if explicit_year and dates else future[0] if future else None
            if selected is None:
                return unknown(ctx, match.group(), "lunar_year_or_leap_month_needs_clarification")
            return make_result(
                ctx,
                start=selected,
                end=selected + timedelta(days=1),
                matched_text=match.group(),
                confidence=0.97 if explicit_year else 0.85,
            )
        except (ValueError, LookupError, AttributeError, TypeError, KeyError):
            return unknown(ctx, match.group(), "lunar_calendar_unavailable")
    malformed = re.search(r"(?:农历|阴历|腊|冬|正)[^，。！？\n]{0,20}月[初廿一二三四五六七八九十\d]+", text)
    return unknown(ctx, malformed.group(), "lunar_date_invalid") if malformed else None


def parse_ambiguous_lunar(text: str, ctx: ParseContext, calendar: CalendarPort) -> TimeRangeResult | None:
    match = PATTERN.search(text)
    if match is None or match["marker"] or match["leap"] or match["month"] in {"正", "冬", "腊"}:
        return None
    if match["year"] or match["year_after"] or match["month"].isdigit():
        return None
    try:
        month, day = chinese_number(match["month"]), chinese_number(match["day"])
        solar = date(ctx.local_date.year, month, day)
        lunar = calendar.lunar_date(ctx.local_date.year, month, day)
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=match.group(),
            confidence=0.3,
            normalized_text="公历或农历（待确认）",
            needs_clarification=True,
            candidates=(day_candidate(solar, ctx, "公历"), day_candidate(lunar, ctx, "农历")),
            reason="lunar_or_solar_ambiguous",
        )
    except (ValueError, LookupError, AttributeError, TypeError, KeyError):
        return unknown(ctx, match.group(), "lunar_or_solar_date_invalid")

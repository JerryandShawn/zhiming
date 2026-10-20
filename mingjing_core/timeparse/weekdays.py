"""Monday-based civil weeks with explicit same-day ambiguity rather than silent rollover."""

import re
from datetime import timedelta

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, absolute_day, make_result

OFFSETS = {"上上": -2, "上": -1, "这": 0, "本": 0, "下": 1, "下下": 2, "": 0}
WEEK = r"(?:周|星期|礼拜)"


def parse_week(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    monday = ctx.local_date - timedelta(days=ctx.local_date.weekday())
    weekend = re.search(r"(下下|下|这|本|上上|上)?(?:个)?周末", text)
    if weekend:
        start = monday + timedelta(days=7 * OFFSETS[weekend.group(1) or ""] + 5)
        end = start + timedelta(days=2)
        return make_result(
            ctx,
            start=start,
            end=end,
            matched_text=weekend.group(),
            granularity="day",
            kind="range",
            normalized_text=f"{start.isoformat()}至{end.isoformat()}（不含结束）",
        )
    match = re.search(rf"(下下|下|这|本|上上|上)?(?:个)?{WEEK}([一二三四五六日天1-7])", text)
    if match:
        return _weekday(match, ctx, monday)
    match = re.search(rf"(下下|下|这|本|上上|上)(?:个)?{WEEK}(?![一二三四五六七八九十零〇日天0-9])", text)
    if not match:
        return None
    start = monday + timedelta(days=7 * OFFSETS[match.group(1)])
    end = start + timedelta(days=7)
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="week",
        kind="range",
        normalized_text=f"{start.isoformat()}至{end.isoformat()}（不含结束）",
    )


def _weekday(match: re.Match, ctx: ParseContext, monday) -> TimeRangeResult:
    prefix, name = match.groups()
    weekday = int(name) - 1 if name.isdigit() else "一二三四五六日天".index(name)
    weekday = min(weekday, 6)
    offset = OFFSETS[prefix or ""]
    day = monday + timedelta(days=offset * 7 + weekday)
    if prefix is None and day < ctx.local_date:
        day += timedelta(days=7)
    candidates = ()
    ambiguous = prefix is None and day == ctx.local_date
    if ambiguous:
        candidates = tuple(
            TimeCandidate(
                make_result(ctx, start=option, end=option + timedelta(days=1), matched_text=match.group()).start,
                make_result(ctx, start=option, end=option + timedelta(days=1), matched_text=match.group()).end,
                normalized_text=absolute_day(option),
            )
            for option in (day, day + timedelta(days=7))
        )
    return make_result(
        ctx,
        start=day,
        end=day + timedelta(days=1),
        matched_text=match.group(),
        confidence=0.5 if ambiguous else 0.95,
        candidates=candidates,
        needs_clarification=ambiguous,
        reason="weekday_same_day" if ambiguous else None,
    )

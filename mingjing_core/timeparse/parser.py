"""One pure parser entry point; unclear time expressions remain proposals, not asserted dates."""

import re
from dataclasses import replace
from datetime import datetime

from .clocks import parse_clock
from .contracts import AbsolutizedText, ParseContext, TimeCandidate, TimeRangeResult, make_result
from .months import parse_civil_date, parse_month, parse_quarter, parse_term, parse_year
from .recurrence import parse_recurring
from .relative import parse_duration, parse_relative_day
from .weekdays import parse_week


def _basic(text: str, ctx: ParseContext, calendar: object) -> TimeRangeResult:
    from .calendar_expressions import parse_calendar

    strategies = (
        lambda value, context: parse_calendar(value, context, calendar),
        parse_recurring,
        parse_civil_date,
        parse_duration,
        parse_week,
        parse_relative_day,
        parse_month,
        parse_quarter,
        parse_term,
        parse_year,
    )
    result = None
    for strategy in strategies:
        result = strategy(text, ctx)
        if result is not None:
            break
    if (
        result is None
        or result.start is not None
        and result.granularity == "day"
        and result.kind in {"point", "recurring"}
    ):
        clock = parse_clock(text, ctx, result)
        if clock is not None:
            return clock
    return result or make_result(ctx, start=None, end=None, matched_text="", confidence=0, granularity="unknown")


def _candidate(result: TimeRangeResult) -> TimeCandidate:
    return TimeCandidate(
        result.start, result.end, result.granularity, result.kind, result.confidence, result.normalized_text
    )


def _compound(text: str, ctx: ParseContext, calendar: object) -> TimeRangeResult | None:
    match = re.search(r"或者|还是|或|和|到|至", text)
    if not match:
        return None
    pieces = (text[: match.start()], text[match.end() :])
    results = [_basic(piece, ParseContext(ctx.ref_time, ctx.tz, piece), calendar) for piece in pieces]
    if not all(item.start is not None for item in results):
        return None
    left, right = results
    if (
        match.group() in {"到", "至"}
        and not any(item.needs_clarification for item in results)
        and right.end is not None
        and right.end >= left.start
    ):
        return make_result(
            ctx,
            start=left.start,
            end=right.end,
            matched_text=text,
            granularity="range",
            kind="range",
            confidence=min(left.confidence, right.confidence),
            normalized_text=f"{left.normalized_text}至{right.normalized_text}",
        )
    return make_result(
        ctx,
        start=left.start,
        end=left.end,
        matched_text=text,
        granularity=left.granularity,
        kind=left.kind,
        confidence=0.45,
        needs_clarification=True,
        candidates=tuple(_candidate(item) for item in results),
        reason="multiple_time_interpretations",
        normalized_text=" / ".join(item.normalized_text for item in results),
    )


def _disjoint(text: str, ctx: ParseContext, calendar: object) -> TimeRangeResult:
    first = _basic(text, ctx, calendar)
    if first.span is None or first.start is None:
        return first
    lower, upper = first.span
    remaining = text[:lower] + " " * (upper - lower) + text[upper:]
    second = _basic(remaining, ParseContext(ctx.ref_time, ctx.tz, remaining), calendar)
    if second.start is None or (second.start, second.end) == (first.start, first.end):
        return first
    if second.matched_text == "今年" and first.start.astimezone(ctx.zone).year == ctx.local_date.year:
        return first
    return make_result(
        ctx,
        start=first.start,
        end=first.end,
        matched_text=text,
        granularity=first.granularity,
        kind=first.kind,
        confidence=0.45,
        candidates=(_candidate(first), _candidate(second)),
        needs_clarification=True,
        reason="multiple_time_expressions",
        normalized_text=f"{first.normalized_text} / {second.normalized_text}",
    )


def parse_time_range(
    text: str, ref_time: datetime, tz: str = "Asia/Shanghai", calendar: object = None
) -> TimeRangeResult:
    if not isinstance(text, str):
        raise ValueError("待解析内容需要是文字")
    ctx = ParseContext(ref_time, tz, text)
    if len(text) > 100_000:
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text="",
            confidence=0,
            needs_clarification=True,
            granularity="unknown",
            reason="input_too_long",
        )
    try:
        return _compound(text, ctx, calendar) or _disjoint(text, ctx, calendar)
    except (ValueError, ArithmeticError):
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text="",
            confidence=0,
            needs_clarification=True,
            granularity="unknown",
            reason="invalid_or_unsupported_time_expression",
        )


def absolutize(text: str, ref_time: datetime, tz: str = "Asia/Shanghai", calendar: object = None) -> AbsolutizedText:
    result = parse_time_range(text, ref_time, tz, calendar)
    if result.needs_clarification or result.start is None or result.span is None or result.kind == "recurring":
        return AbsolutizedText(text, text, result, False)
    start, end = result.span
    replacement = result.normalized_text
    changed = text[:start] + replacement + text[end:]
    return AbsolutizedText(text, changed, replace(result, original_text=text), changed != text)

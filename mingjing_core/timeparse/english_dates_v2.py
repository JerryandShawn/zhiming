"""Additive English/mixed parser. Source spans are original slices, never translated indices.

Relative civil dates use the caller's explicit ``tz``. A clock's explicit zone
changes that clock's wall-time interpretation, not an already stated civil date.
No English locale is guessed for slash dates, weekday 'next', or zone abbreviations.
"""

import re
from dataclasses import replace
from datetime import datetime

from .clocks import parse_clock
from .contracts import ParseContext, TimeRangeResult
from .english_absolute_v2 import absolute_atoms
from .english_calendar_v2 import calendar_atoms
from .english_clocks_v2 import apply_clock, clock_atoms
from .english_helpers_v2 import alternatives, exact_span, invalid, nonoverlapping
from .english_relative_v2 import recurring_atom, relative_atoms
from .parser import parse_time_range


def parse_english_date(
    text: str, ref_time: datetime, tz: str = "Asia/Shanghai", calendar=None
) -> TimeRangeResult | None:
    ctx = ParseContext(ref_time, tz, text)
    if len(text) > 100_000:
        return invalid(ctx, text, "input_too_long")
    recurring = recurring_atom(ctx)
    if recurring is not None:
        return recurring
    dates = nonoverlapping(
        (*absolute_atoms(ctx, calendar), *relative_atoms(ctx, calendar), *calendar_atoms(ctx, calendar))
    )
    clocks = clock_atoms(ctx)
    if not dates and not clocks:
        return None
    masked = _mask(text, [item.span for item in dates] + [item.span for item in clocks])
    chinese = parse_time_range(masked, ref_time, tz, calendar)
    if chinese.span and chinese.granularity not in {"unknown", "minute", "hour"}:
        dates.append(exact_span(chinese, chinese.span, ctx))
    if len(dates) > 1:
        return _multiple(ctx, dates, "multiple_time_expressions")
    if len(clocks) > 1:
        options = [apply_clock(clock, ctx, dates[0] if dates else None) for clock in clocks]
        return _multiple(ctx, options, "multiple_clock_expressions")
    base = dates[0] if dates else None
    if clocks:
        chinese_clock = parse_clock(masked, ParseContext(ref_time, tz, masked), base)
        result = apply_clock(clocks[0], ctx, base)
        if chinese_clock is not None:
            return _multiple(ctx, (result, chinese_clock), "multiple_clock_expressions")
        return _contiguous(result, base, clocks[0].span, ctx)
    chinese_clock = parse_clock(text, ctx, base)
    if chinese_clock and chinese.span and chinese.granularity in {"minute", "hour"}:
        return _contiguous(chinese_clock, base, chinese.span, ctx)
    return chinese_clock or base


def _mask(text: str, spans) -> str:
    chars = list(text)
    for span in spans:
        if span is not None:
            chars[span[0] : span[1]] = " " * (span[1] - span[0])
    return "".join(chars)


def _multiple(ctx: ParseContext, results, reason: str) -> TimeRangeResult:
    result = alternatives(ctx, ctx.text, results, reason)
    # A composite is deliberately not a replaceable single memory event span.
    return replace(result, original_text=ctx.text, matched_text=ctx.text, span=(0, len(ctx.text)))


def _contiguous(
    result: TimeRangeResult, base: TimeRangeResult | None, clock_span, ctx: ParseContext
) -> TimeRangeResult:
    if base is None or base.span is None or result.needs_clarification:
        return result
    left, right = (base.span[1], clock_span[0]) if base.span[1] <= clock_span[0] else (clock_span[1], base.span[0])
    gap = ctx.text[left:right] if left <= right else ""
    if re.fullmatch(r"[\s,，:：]*(?:(?:at|on|的|在|T)[\s,，:：]*)?", gap, re.I):
        return result
    return _multiple(ctx, (result,), "noncontiguous_date_clock_spans")

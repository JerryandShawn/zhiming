"""Source-span preserving bridges to the frozen Chinese parser; no calendar data is copied."""

from dataclasses import replace
from datetime import timedelta

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, bind_text, make_result
from .parser import parse_time_range

LEFT = r"(?<![A-Za-z0-9_])(?<![A-Za-z][-‐‑–])"
RIGHT = r"(?![A-Za-z0-9_]|[-‐‑–][A-Za-z])"


def translated(expression: str, matched: str, ctx: ParseContext, calendar=None) -> TimeRangeResult:
    result = parse_time_range(expression, ctx.ref_time, ctx.tz, calendar)
    return bind_text(result, ctx, matched)


def invalid(ctx: ParseContext, matched: str, reason: str) -> TimeRangeResult:
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=matched,
        confidence=0,
        needs_clarification=True,
        reason=reason,
        granularity="unknown",
    )


def candidate(result: TimeRangeResult) -> TimeCandidate:
    return TimeCandidate(
        result.start, result.end, result.granularity, result.kind, min(result.confidence, 0.5), result.normalized_text
    )


def alternatives(ctx: ParseContext, matched: str, results, reason: str) -> TimeRangeResult:
    options = tuple(option for item in results for option in (item.candidates or (candidate(item),)))
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=matched,
        granularity=results[0].granularity if results else "unknown",
        confidence=0.4,
        candidates=options,
        needs_clarification=True,
        reason=reason,
        normalized_text=" / ".join(item.normalized_text for item in options),
    )


def day_result(ctx: ParseContext, matched: str, day) -> TimeRangeResult:
    return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=matched)


def exact_span(result: TimeRangeResult, span: tuple[int, int], ctx: ParseContext) -> TimeRangeResult:
    return replace(result, original_text=ctx.text, matched_text=ctx.text[slice(*span)], span=span)


def nonoverlapping(results) -> list[TimeRangeResult]:
    accepted = []
    for result in sorted(results, key=lambda item: (item.span[0], -(item.span[1] - item.span[0]))):
        if not any(result.span[0] < prior.span[1] and prior.span[0] < result.span[1] for prior in accepted):
            accepted.append(result)
    return accepted

"""Opt-in composition of Q1 Chinese, English and explicitly injected profile dates."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from typing import TYPE_CHECKING

from .contracts import AbsolutizedText, ParseContext, TimeCandidate, TimeRangeResult, make_result
from .parser import parse_time_range

if TYPE_CHECKING:
    from .profile_contracts_v2 import ProfileDatePort, ProfileScope


def _useful(result: TimeRangeResult | None) -> bool:
    return result is not None and (result.span is not None or result.needs_clarification)


def _contains(outer: TimeRangeResult, inner: TimeRangeResult) -> bool:
    if outer.span is None or inner.span is None or outer.span == inner.span:
        return False
    return outer.span[0] <= inner.span[0] and outer.span[1] >= inner.span[1]


def _chinese_span_safety(result: TimeRangeResult, ctx: ParseContext, calendar: object) -> TimeRangeResult:
    from .clocks import _match

    if result.needs_clarification or result.granularity != "minute" or result.span is None:
        return result
    clock = _match(ctx.text)
    if clock is None:
        return result
    masked = ctx.text[: clock.start()] + " " * (clock.end() - clock.start()) + ctx.text[clock.end() :]
    base = parse_time_range(masked, ctx.ref_time, ctx.tz, calendar)
    if base.span is None or base.granularity != "day":
        return result
    left, right = (base.span[1], clock.start()) if base.span[1] <= clock.start() else (clock.end(), base.span[0])
    gap = ctx.text[left:right] if left <= right else ""
    if re.fullmatch(r"[\s:：]*(?:(?:的|在|于|at|T)[\s:：]*)?", gap, re.I):
        return result
    return replace(
        result,
        confidence=0.35,
        needs_clarification=True,
        candidates=_candidates([result]),
        reason="noncontiguous_date_clock_spans",
    )


def _candidates(results: list[TimeRangeResult]) -> tuple[TimeCandidate, ...]:
    seen, values = set(), []
    for result in results:
        for item in result.candidates or (result,):
            key = item.start, item.end, item.granularity, item.kind, item.normalized_text
            if key in seen:
                continue
            seen.add(key)
            values.append(
                TimeCandidate(
                    item.start,
                    item.end,
                    item.granularity,
                    item.kind,
                    min(item.confidence, 0.45),
                    item.normalized_text,
                    item.label,
                )
            )
    return tuple(values[:16])


def _select(results: list[TimeRangeResult], ctx: ParseContext, profile: TimeRangeResult | None) -> TimeRangeResult:
    if profile is not None and profile.needs_clarification:
        return (
            replace(profile, kind="recurring", recurrence=None)
            if any(item.kind == "recurring" for item in results)
            else profile
        )
    # An English date+Chinese clock may contain the old parser's clock-only interpretation.
    retained = [item for item in results if not any(_contains(other, item) for other in results)]
    unique = {}
    for item in retained:
        key = item.span, item.start, item.end, item.granularity, item.kind, item.needs_clarification
        unique.setdefault(key, item)
    retained = list(unique.values())
    if len(retained) == 1:
        return retained[0]
    candidates = _candidates(retained)
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=ctx.text,
        confidence=0.35,
        normalized_text=" / ".join(item.normalized_text for item in candidates if item.normalized_text),
        candidates=candidates,
        needs_clarification=True,
        granularity="unknown",
        reason="multiple_time_expressions",
    )


def parse_time_range_extended(
    text: str,
    ref_time: datetime,
    tz: str = "Asia/Shanghai",
    calendar: object = None,
    *,
    profile_scope: ProfileScope | None = None,
    profiles: ProfileDatePort | None = None,
) -> TimeRangeResult:
    """No ambient profile identity. Ambiguous/untrusted dates remain clarification proposals."""
    from .english_dates_v2 import parse_english_date
    from .profile_dates_v2 import parse_profile_date

    ctx = ParseContext(ref_time, tz, text)
    chinese = parse_time_range(text, ref_time, tz, calendar)
    if len(text) > 100_000:
        return chinese
    chinese = _chinese_span_safety(chinese, ctx, calendar)
    english = parse_english_date(text, ref_time, tz, calendar)
    profile = parse_profile_date(text, ref_time, tz, scope=profile_scope, profiles=profiles, calendar=calendar)
    results = [item for item in (profile, english, chinese) if _useful(item)]
    if not results:
        return chinese
    return _select(results, ctx, profile)


def absolutize_extended(
    text: str,
    ref_time: datetime,
    tz: str = "Asia/Shanghai",
    calendar: object = None,
    *,
    profile_scope: ProfileScope | None = None,
    profiles: ProfileDatePort | None = None,
) -> AbsolutizedText:
    result = parse_time_range_extended(
        text,
        ref_time,
        tz,
        calendar,
        profile_scope=profile_scope,
        profiles=profiles,
    )
    if result.needs_clarification or result.start is None or result.span is None or result.kind == "recurring":
        return AbsolutizedText(text, text, result, False)
    lower, upper = result.span
    if not 0 <= lower < upper <= len(text) or text[lower:upper] != result.matched_text:
        raise ValueError("时间解析跨度与原文不一致")
    normalized = text[:lower] + result.normalized_text + text[upper:]
    return AbsolutizedText(text, normalized, replace(result, original_text=text), normalized != text)

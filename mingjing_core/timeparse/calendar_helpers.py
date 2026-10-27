"""Shared linguistic helpers only; dated holiday data stays inside P2."""

import re
from datetime import date, timedelta

from .calendar_port import CalendarPort
from .contracts import ParseContext, TimeCandidate, TimeRangeResult, absolute_day, local_midnight, make_result

YEAR_PATTERN = r"(?:(?P<year>前年|去年|今年|明年|后年|[12]\d{3})年?的?)?"


def specified_year(raw: str | None, ctx: ParseContext) -> int | None:
    if not raw:
        return None
    offsets = {"前年": -2, "去年": -1, "今年": 0, "明年": 1, "后年": 2}
    return ctx.local_date.year + offsets[raw] if raw in offsets else int(raw)


def day_candidate(day: date, ctx: ParseContext, label: str, confidence: float = 0.55) -> TimeCandidate:
    return TimeCandidate(
        local_midnight(day, ctx),
        local_midnight(day + timedelta(days=1), ctx),
        confidence=confidence,
        normalized_text=absolute_day(day),
        label=label,
    )


def unknown(ctx: ParseContext, matched: str, reason: str, *, day: date | None = None) -> TimeRangeResult:
    return make_result(
        ctx,
        start=day,
        end=day + timedelta(days=1) if day else None,
        matched_text=matched,
        confidence=0.2,
        needs_clarification=True,
        reason=reason,
        normalized_text="日期范围待确认" if day is None else absolute_day(day),
    )


def vague_around(ctx: ParseContext, matched: str, day: date, direction: str) -> TimeRangeResult:
    if direction in {"前", "之前"}:
        candidates = (
            day_candidate(day - timedelta(days=1), ctx, "前一天"),
            _week_candidate(ctx, day - timedelta(days=7), day, "之前一周"),
        )
    elif direction in {"后", "之后"}:
        candidates = (
            day_candidate(day + timedelta(days=1), ctx, "后一天"),
            _week_candidate(ctx, day + timedelta(days=1), day + timedelta(days=8), "之后一周"),
        )
    else:
        candidates = (
            _week_candidate(ctx, day - timedelta(days=7), day, "之前一周"),
            _week_candidate(ctx, day, day + timedelta(days=8), "当天及之后一周"),
        )
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=matched,
        granularity="fuzzy",
        kind="range",
        confidence=0.4,
        candidates=candidates,
        needs_clarification=True,
        normalized_text=f"{absolute_day(day)}{direction}（范围待确认）",
        reason="unspecified_horizon",
    )


def _week_candidate(ctx: ParseContext, start: date, end: date, label: str) -> TimeCandidate:
    return TimeCandidate(local_midnight(start, ctx), local_midnight(end, ctx), "week", "range", 0.4, label, label)


def first_workday(calendar: CalendarPort, after: date) -> date | None:
    for offset in range(1, 32):
        day = after + timedelta(days=offset)
        status = calendar.day_status(day)
        if status.source == "unpublished":
            return None
        if not status.is_off:
            return day
    return None


def chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {
        "〇": 0,
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "正": 1,
        "冬": 11,
        "腊": 12,
    }
    value = value.removeprefix("初")
    if value.startswith("廿"):
        return 20 + (digits[value[1:]] if value[1:] else 0)
    if "十" in value:
        left, right = value.split("十", maxsplit=1)
        return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
    if len(value) > 1 and re.fullmatch("[〇零一二三四五六七八九]+", value):
        return int("".join(str(digits[character]) for character in value))
    return digits[value]

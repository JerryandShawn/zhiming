"""Relative English phrases keep civil-day and Monday-week semantics of U4."""

import re
from datetime import timedelta

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, make_result
from .english_helpers_v2 import LEFT, RIGHT, alternatives, day_result, exact_span, invalid, translated

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY = "(?:" + "|".join(name + "|" + name[:3] for name in WEEKDAYS) + ")"
RELATIVE = re.compile(
    LEFT + rf"(?:day\s+after\s+tomorrow|day\s+before\s+yesterday|today|tomorrow|yesterday|"
    rf"(?:this|next|following|last)\s+week(?:\s+(?:on\s+)?{DAY})?|"
    rf"{DAY}\s+(?:of\s+)?(?:this|next|following|last)\s+week|"
    rf"(?:(?:this|next|following|last)\s+)?weekend|"
    rf"(?:(?:this|next|last)\s+)?{DAY})" + RIGHT,
    re.I,
)
WORDS = dict(
    zip(
        (
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
        ),
        range(1, 21),
        strict=True,
    )
)
WORDS.update(a=1, an=1)
NUMBER = r"(?:-?\d+(?:\.\d+)?|" + "|".join(WORDS) + ")"
RECURRENCE = re.compile(
    LEFT + rf"(?:(?:every|each)\s+(?:(?:other|first|second|third|fourth|last|single|{NUMBER})\s+)?"
    rf"(?:(?:(?:business|working)\s+)?days?|weeks?|months?|years?|weekdays?|weekends?|mornings?|evenings?|"
    rf"{DAY}s?|天|周[一二三四五六日天]?|月|年)|"
    r"daily|weekly|monthly|yearly|annually)" + RIGHT,
    re.I,
)
DURATION = re.compile(LEFT + rf"(?:in|within)\s+({NUMBER})\s+(days?|weeks?)" + RIGHT, re.I)
QUARTER = re.compile(
    LEFT + r"(?:(?:this|next|last|following)\s+quarter|\d{4}\s+Q\d+|Q\d+(?:\s+(?:of\s+)?\d{4})?|"
    r"(?:first|second|third|fourth|\d+(?:st|nd|rd|th))\s+quarter(?:\s+(?:of\s+)?\d{4})?)" + RIGHT,
    re.I,
)


def recurring_atom(ctx: ParseContext) -> TimeRangeResult | None:
    if RECURRENCE.search(ctx.text) is None:
        return None
    label = "英文循环意图需确认，尚未计算下次时间"
    option = TimeCandidate(None, None, "recurrence", "recurring", 0.25, label)
    # The unsupported rule scopes the entire utterance, including any accompanying clock.
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=ctx.text,
        granularity="recurrence",
        kind="recurring",
        confidence=0.25,
        normalized_text=label,
        candidates=(option,),
        needs_clarification=True,
        reason="unsupported_english_recurrence",
    )


def relative_atoms(ctx: ParseContext, calendar=None) -> list[TimeRangeResult]:
    results = []
    for pattern, parser in ((RELATIVE, _relative), (DURATION, _duration), (QUARTER, _quarter)):
        for match in pattern.finditer(ctx.text):
            try:
                result = parser(match.group(), ctx, calendar)
            except (ValueError, ArithmeticError):
                result = invalid(ctx, match.group(), "invalid_english_time_expression")
            results.append(exact_span(result, match.span(), ctx))
    return results


def _weekday(name: str) -> int:
    return next(index for index, day in enumerate(WEEKDAYS) if name in {day, day[:3]})


def _relative(raw: str, ctx: ParseContext, calendar) -> TimeRangeResult:
    clean = " ".join(raw.lower().split())
    days = {
        "today": "今天",
        "tomorrow": "明天",
        "yesterday": "昨天",
        "day after tomorrow": "后天",
        "day before yesterday": "前天",
    }
    if clean in days:
        return translated(days[clean], raw, ctx, calendar)
    shift_match = re.search(r"this|next|following|last", clean)
    shift = shift_match.group() if shift_match else ""
    prefix = {"this": "本", "next": "下", "following": "下", "last": "上", "": ""}[shift]
    if "weekend" in clean:
        return translated(prefix + "周末", raw, ctx, calendar)
    weekday = re.search(DAY, clean)
    if weekday is None:
        return translated(prefix + "周", raw, ctx, calendar)
    number = _weekday(weekday.group())
    if shift == "next" and "week" not in clean:
        return _next_weekday(raw, number, ctx)
    return translated(prefix + "周" + "一二三四五六日"[number], raw, ctx, calendar)


def _next_weekday(raw: str, number: int, ctx: ParseContext) -> TimeRangeResult:
    distance = (number - ctx.local_date.weekday()) % 7 or 7
    upcoming = ctx.local_date + timedelta(days=distance)
    next_week = ctx.local_date + timedelta(days=7 - ctx.local_date.weekday() + number)
    results = [day_result(ctx, raw, day) for day in dict.fromkeys((upcoming, next_week))]
    return alternatives(ctx, raw, results, "next_weekday_semantics")


def _duration(raw: str, ctx: ParseContext, calendar) -> TimeRangeResult:
    match = DURATION.fullmatch(raw)
    value = match.group(1).lower()
    amount = WORDS[value] if value in WORDS else float(value)
    if amount <= 0 or amount > 1000 or int(amount) != amount:
        return invalid(ctx, raw, "invalid_or_fractional_civil_duration")
    unit = "周" if match.group(2).lower().startswith("week") else "天"
    direction = "内" if raw.lower().startswith("within") else "后"
    return translated(f"{int(amount)}{unit}{direction}", raw, ctx, calendar)


def _quarter(raw: str, ctx: ParseContext, calendar) -> TimeRangeResult:
    clean = raw.lower()
    shift = re.search(r"this|next|last|following", clean)
    if shift:
        expression = {"this": "本季度", "next": "下季度", "last": "上季度", "following": "下季度"}[shift.group()]
    else:
        value = re.search(r"q(\d+)", clean)
        if value:
            number = int(value.group(1))
        elif clean[0].isdigit():
            number = int(re.match(r"\d+", clean).group())
        else:
            number = ("first", "second", "third", "fourth").index(clean.split()[0]) + 1
        if number not in range(1, 5):
            return invalid(ctx, raw, "invalid_quarter")
        year = re.search(r"\d{4}", clean)
        expression = (year.group() + "年" if year else "") + f"第{number}季度"
    return translated(expression, raw, ctx, calendar)

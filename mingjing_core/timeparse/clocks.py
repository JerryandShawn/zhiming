"""Explicit wall-clock rules, including the intentionally ambiguous 今晚凌晨 form."""

import re
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta

from .contracts import WEEKDAYS, ParseContext, TimeCandidate, TimeRangeResult, make_result
from .numerals import NUMBER, parse_number

PERIOD = r"凌晨|早上|上午|中午|下午|傍晚|晚上|晚间|夜里|半夜|清晨|今晚|明晚|今早|明早"
PARTS = {
    "中午": (11, 13),
    "傍晚": (17, 19),
    "上午": (8, 12),
    "下午": (13, 18),
    "晚上": (19, 23),
    "凌晨": (0, 6),
    "早上": (6, 10),
    "清晨": (5, 8),
    "今晚": (19, 23),
    "明晚": (19, 23),
}


def _label(value: datetime, ctx: ParseContext) -> str:
    local = value.astimezone(ctx.zone)
    return f"{local.date().isoformat()}（周{WEEKDAYS[local.weekday()]}）{local:%H:%M}"


def _match(text: str):
    return re.search(
        rf"(?<![-\d])(?P<period>{PERIOD})?(?P<hour>{NUMBER})(?:点|时|:|：)(?P<minute>半|一刻|三刻|{NUMBER}分?)?", text
    )


def _values(match: re.Match) -> tuple[int, int, bool]:
    hour = parse_number(match.group("hour"))
    raw = match.group("minute") or "零"
    minute = {"半": 30, "一刻": 15, "三刻": 45}.get(raw)
    if minute is None:
        minute = parse_number(raw.rstrip("分"))
    period = match.group("period")
    if (
        period in {"上午", "早上", "清晨", "今早", "明早"}
        and hour > 12
        or period in {"凌晨", "半夜"}
        and hour not in {*range(7), 12}
    ):
        return -1, minute, False
    if (
        period in {"下午", "傍晚", "晚上", "晚间", "夜里", "今晚", "明晚"}
        and 1 <= hour <= 11
        or period == "中午"
        and 1 <= hour <= 3
    ):
        hour += 12
    elif period in {"凌晨", "半夜", "晚上", "晚间", "夜里", "今晚", "明晚"} and hour == 12:
        hour = 0
    ambiguous = period is None and "点" in match.group() and hour <= 12
    return hour, minute, ambiguous


def parse_clock(text: str, ctx: ParseContext, base: TimeRangeResult | None = None) -> TimeRangeResult | None:
    match = _match(text)
    if match is None:
        return _part(text, ctx, base)
    if _separate(text, base, match.start(), match.end()):
        return None
    hour, minute, ambiguous = _values(match)
    matched = _matched(text, base, match.start(), match.end())
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=matched,
            confidence=0,
            needs_clarification=True,
            reason="invalid_clock",
        )
    day = base.start.astimezone(ctx.zone).date() if base and base.start else ctx.local_date
    if match.group("period") in {"晚上", "晚间", "夜里", "今晚", "明晚"} and parse_number(match.group("hour")) in {
        0,
        12,
    }:
        day += timedelta(days=1)
    stamp = datetime.combine(day, time(hour, minute), ctx.zone)
    dst = _dst_result(stamp, ctx, matched)
    if dst is not None:
        return dst
    stamps = [stamp]
    reason = None
    if "今晚凌晨" in text:
        stamps.append(stamp + timedelta(days=1))
        reason = "tonight_after_midnight"
    elif ambiguous:
        stamps.append(stamp.replace(hour=(hour + 12) % 24))
        reason = "missing_am_pm"
    elif base is None and stamp < ctx.local_ref:
        stamps.append(stamp + timedelta(days=1))
        reason = "clock_date_unspecified"
    candidates = tuple(TimeCandidate(value, value, "minute", "point", 0.5, _label(value, ctx)) for value in stamps)
    result = make_result(
        ctx,
        start=stamp,
        end=stamp,
        matched_text=matched,
        granularity="minute",
        confidence=0.5 if reason else 0.95,
        normalized_text=_label(stamp, ctx),
        candidates=candidates if reason else (),
        needs_clarification=bool(reason),
        reason=reason,
    )
    return _finish_clock(base, result, reason, hour, minute, ctx)


def _finish_clock(
    base: TimeRangeResult | None, result: TimeRangeResult, reason: str | None, hour: int, minute: int, ctx: ParseContext
) -> TimeRangeResult:
    if base and base.needs_clarification and not reason:
        result = replace(
            result,
            needs_clarification=True,
            confidence=min(base.confidence, 0.5),
            reason=base.reason,
            candidates=tuple(_candidate_clock(option, hour, minute, ctx) for option in base.candidates if option.start),
        )
    if base and base.kind == "recurring":
        suffix = f";time={hour:02}:{minute:02}" if not result.needs_clarification else ""
        return replace(result, kind="recurring", recurrence=f"{base.recurrence}{suffix}")
    return result


def _dst_result(stamp: datetime, ctx: ParseContext, matched: str) -> TimeRangeResult | None:
    alternatives = [stamp.replace(fold=fold).astimezone(UTC).astimezone(ctx.zone) for fold in (0, 1)]
    if alternatives[0].utcoffset() == alternatives[1].utcoffset():
        return None
    nonexistent = any(value.replace(tzinfo=None) != stamp.replace(tzinfo=None) for value in alternatives)
    candidates = tuple(
        TimeCandidate(value, value, "minute", "point", 0.3, f"{_label(value, ctx)} ({value:%z})")
        for value in alternatives
    )
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=matched,
        granularity="minute",
        confidence=0.3,
        candidates=candidates,
        needs_clarification=True,
        reason="nonexistent_wall_clock" if nonexistent else "ambiguous_wall_clock",
        normalized_text=" / ".join(candidate.normalized_text for candidate in candidates),
    )


def _candidate_clock(option: TimeCandidate, hour: int, minute: int, ctx: ParseContext) -> TimeCandidate:
    stamp = datetime.combine(option.start.astimezone(ctx.zone).date(), time(hour, minute), ctx.zone)
    return replace(option, start=stamp, end=stamp, normalized_text=_label(stamp, ctx), granularity="minute")


def _separate(text: str, base: TimeRangeResult | None, start: int, end: int) -> bool:
    if base is None or base.span is None:
        return False
    lower, upper = (base.span[1], start) if base.span[1] <= start else (end, base.span[0])
    between = text[lower:upper]
    return bool(re.search(r"[，,；;。]|今天|明天|后天|昨天|前天|(?:下|本|这)?周[一二三四五六日天]", between))


def _matched(text: str, base: TimeRangeResult | None, start: int, end: int) -> str:
    if base and base.span:
        start, end = min(start, base.span[0]), max(end, base.span[1])
    return text[start:end]


def _part(text: str, ctx: ParseContext, base: TimeRangeResult | None) -> TimeRangeResult | None:
    match = re.search("|".join(PARTS), text)
    if not match:
        return None
    if _separate(text, base, match.start(), match.end()):
        return None
    day = base.start.astimezone(ctx.zone).date() if base and base.start else ctx.local_date
    left, right = PARTS[match.group()]
    start, end = datetime.combine(day, time(left), ctx.zone), datetime.combine(day, time(right), ctx.zone)
    matched = _matched(text, base, match.start(), match.end())
    label = f"{day.isoformat()} {left:02}:00–{right:02}:00（需确认时刻）"
    candidate = TimeCandidate(start, end, "hour", "range", 0.6, label)
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=matched,
        granularity="hour",
        kind="recurring" if base and base.kind == "recurring" else "range",
        confidence=0.6,
        normalized_text=label,
        candidates=(candidate,),
        needs_clarification=True,
        reason="approximate_daypart",
        recurrence=base.recurrence if base and base.kind == "recurring" else None,
    )

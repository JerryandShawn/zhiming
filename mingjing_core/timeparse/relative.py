"""Relative civil days and durations use the supplied reference, never the machine timezone."""

import calendar
import re
from datetime import date, datetime, timedelta

from .contracts import ParseContext, TimeCandidate, TimeRangeResult, make_result
from .numerals import NUMBER, parse_number

DAY_OFFSETS = {
    "今天": 0,
    "今日": 0,
    "明天": 1,
    "明日": 1,
    "后天": 2,
    "大后天": 3,
    "昨天": -1,
    "昨日": -1,
    "前天": -2,
    "大前天": -3,
    "今晚": 0,
    "今早": 0,
    "明早": 1,
    "明晚": 1,
    "昨晚": -1,
}


def parse_relative_day(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search("|".join(sorted(DAY_OFFSETS, key=len, reverse=True)), text)
    if match is None or re.search(r"后天(?:性|形成|努力|培养)", text):
        return None
    day = ctx.local_date + timedelta(days=DAY_OFFSETS[match.group()])
    return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=match.group())


def shifted_month(value: date | datetime, months: int) -> date | datetime:
    ordinal = value.year * 12 + value.month - 1 + months
    year, month = divmod(ordinal, 12)
    return value.replace(year=year, month=month + 1, day=min(value.day, calendar.monthrange(year, month + 1)[1]))


def _vague(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    match = re.search(r"过[几数]天|[几数]天[后内]|这两天|最近", text)
    if not match:
        return None
    left, right = (-7, 1) if match.group() == "最近" else (0, 3) if match.group() == "这两天" else (2, 8)
    start, end = ctx.local_date + timedelta(days=left), ctx.local_date + timedelta(days=right)
    result = make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="day",
        kind="range",
        confidence=0.35,
        needs_clarification=True,
        reason="vague_duration",
        normalized_text=f"约{start.isoformat()}至{end.isoformat()}（不含结束）",
    )
    candidate = TimeCandidate(result.start, result.end, "day", "range", 0.35, result.normalized_text)
    return make_result(
        ctx,
        start=start,
        end=end,
        matched_text=match.group(),
        granularity="day",
        kind="range",
        confidence=0.35,
        needs_clarification=True,
        candidates=(candidate,),
        reason="vague_duration",
        normalized_text=result.normalized_text,
    )


def parse_duration(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    vague = _vague(text, ctx)
    if vague:
        return vague
    match = re.search(rf"(?:过)?({NUMBER}|半)(分钟|小时|天|日|周|星期|个月|月|年)(之后|以后|后|之内|以内|内|前)", text)
    if not match:
        return None
    raw, unit, direction = match.groups()
    amount = 0.5 if raw == "半" else parse_number(raw)
    if amount <= 0 or amount > 1000 or unit in {"月", "个月", "年"} and amount != int(amount):
        return make_result(
            ctx,
            start=None,
            end=None,
            matched_text=match.group(),
            confidence=0,
            needs_clarification=True,
            reason="invalid_duration",
        )
    sign = -1 if direction == "前" else 1
    local = ctx.local_ref
    if unit in {"月", "个月", "年"}:
        target = shifted_month(local, int(amount) * sign * (12 if unit == "年" else 1))
    else:
        seconds = {"分钟": 60, "小时": 3600, "天": 86400, "日": 86400, "周": 604800, "星期": 604800}[unit]
        delta = timedelta(seconds=amount * sign * seconds)
        target = (
            (ctx.ref_time + delta).astimezone(ctx.zone)
            if unit in {"小时", "分钟"} or amount != int(amount)
            else local + delta
        )
    if direction in {"内", "之内", "以内"}:
        return make_result(
            ctx,
            start=local,
            end=target,
            matched_text=match.group(),
            granularity="duration",
            kind="range",
            normalized_text=f"{local.isoformat()}至{target.isoformat()}（不含结束）",
        )
    if unit in {"小时", "分钟"} or amount != int(amount):
        return make_result(
            ctx,
            start=target,
            end=target,
            matched_text=match.group(),
            granularity="minute",
            normalized_text=target.isoformat(),
        )
    day = target.date()
    return make_result(ctx, start=day, end=day + timedelta(days=1), matched_text=match.group())

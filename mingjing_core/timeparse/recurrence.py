"""Recurring civil rule descriptions; execution and claim-time lateness belong to the scheduler."""

import re
from datetime import date, timedelta

from .contracts import ParseContext, TimeRangeResult, make_result
from .numerals import NUMBER, parse_number
from .relative import shifted_month


def parse_recurring(text: str, ctx: ParseContext) -> TimeRangeResult | None:
    weekly = re.search(r"每(?:个)?(?:周|星期|礼拜)([一二三四五六日天1-7])", text)
    if weekly:
        raw = weekly.group(1)
        weekday = int(raw) - 1 if raw.isdigit() else min("一二三四五六日天".index(raw), 6)
        day = ctx.local_date + timedelta(days=(weekday - ctx.local_date.weekday()) % 7)
        return _rule(ctx, day, weekly.group(), f"weekly:weekday={weekday}")
    daily = re.search(r"每天|每日|每一天", text)
    if daily:
        return _rule(ctx, ctx.local_date, daily.group(), "daily")
    monthly = re.search(rf"每(?:个)?月({NUMBER})[日号]", text)
    if monthly:
        return _monthly(monthly, ctx)
    yearly = re.search(rf"每年(?:公历)?({NUMBER})月({NUMBER})[日号]", text)
    if yearly:
        return _yearly(yearly, ctx)
    return None


def _rule(ctx: ParseContext, day: date, matched: str, recurrence: str) -> TimeRangeResult:
    return make_result(
        ctx,
        start=day,
        end=day + timedelta(days=1),
        matched_text=matched,
        kind="recurring",
        recurrence=recurrence,
        normalized_text=f"{matched}（下次日期{day.isoformat()}）",
    )


def _monthly(match: re.Match, ctx: ParseContext) -> TimeRangeResult:
    day_number = parse_number(match.group(1))
    if 1 <= day_number <= 31:
        for offset in range(25):
            anchor = shifted_month(ctx.local_date.replace(day=1), offset)
            try:
                day = anchor.replace(day=day_number)
            except ValueError:
                continue
            if day >= ctx.local_date:
                return _rule(ctx, day, match.group(), f"monthly:day={day_number};missing=skip")
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=match.group(),
        kind="recurring",
        confidence=0,
        needs_clarification=True,
        reason="invalid_monthly_rule",
    )


def _yearly(match: re.Match, ctx: ParseContext) -> TimeRangeResult:
    month, day_number = parse_number(match.group(1)), parse_number(match.group(2))
    for offset in range(9):
        try:
            day = date(ctx.local_date.year + offset, month, day_number)
        except ValueError:
            continue
        if day >= ctx.local_date:
            return _rule(ctx, day, match.group(), f"yearly:month={month};day={day_number};missing=skip")
    return make_result(
        ctx,
        start=None,
        end=None,
        matched_text=match.group(),
        kind="recurring",
        confidence=0,
        needs_clarification=True,
        reason="invalid_yearly_rule",
    )

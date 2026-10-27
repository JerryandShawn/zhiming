"""Civil dates are computed from the supplied Clock and owner timezone, never a model."""

import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from .structural_contracts import StructuralContext, StructuralFinding

DATE_BODY = r"(?<![\d])(?:(?P<year>\d{4})[年/-])?(?P<month>\d{1,2})[月/-](?P<day>\d{1,2})日?"
WEEKDAY_PATTERN = re.compile(DATE_BODY + r"\s*[（(]\s*(?:周|星期)(?P<weekday>[一二三四五六日天])\s*[）)]")
RELATIVE_PATTERN = re.compile(r"(?P<relative>今天|明天|后天|昨天)(?:是|在|的)?\s*" + DATE_BODY)
DAY_OFFSETS = {"今天": 0, "明天": 1, "后天": 2, "昨天": -1}
WEEKDAYS = "一二三四五六日"


def civil_today(context: StructuralContext) -> date:
    instant = context.clock.now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("结构检查需要有时区的时钟")
    return instant.astimezone(ZoneInfo(context.timezone)).date()


def _date(match: re.Match[str], today: date) -> date | None:
    explicit = match.group("year")
    years = [int(explicit)] if explicit else [today.year - 1, today.year, today.year + 1]
    candidates = []
    for year in years:
        try:
            candidate = date(year, int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        if explicit or abs((candidate - today).days) <= 183:
            candidates.append(candidate)
    return candidates[0] if len(candidates) == 1 else None


def fix_weekdays(text: str, context: StructuralContext) -> tuple[str, list[StructuralFinding]]:
    today = civil_today(context)
    findings = []

    def substitute(match: re.Match[str]) -> str:
        day = _date(match, today)
        if day is None:
            findings.append(
                StructuralFinding("date_unresolved", None, 2, match.group(0), "日期年份或日期本身不能唯一确定")
            )
            return match.group(0)
        actual = WEEKDAYS[day.weekday()]
        if match.group("weekday").replace("天", "日") == actual:
            return match.group(0)
        findings.append(
            StructuralFinding(
                "weekday_fixed",
                "E1",
                5,
                match.group(0),
                "星期必须匹配实际日期",
                "clock:" + day.isoformat(),
                "已按确定性历法改正",
            )
        )
        start = match.start("weekday") - match.start()
        return match.group(0)[:start] + actual + match.group(0)[start + 1 :]

    return WEEKDAY_PATTERN.sub(substitute, text), findings


def check_relative_dates(text: str, context: StructuralContext) -> tuple[str, list[StructuralFinding]]:
    today = civil_today(context)
    findings = []

    def substitute(match: re.Match[str]) -> str:
        expected = today + timedelta(days=DAY_OFFSETS[match.group("relative")])
        mentioned = _date(match, today)
        if mentioned is None:
            findings.append(StructuralFinding("date_unresolved", None, 2, match.group(0), "日期本身或年份不能唯一确定"))
            return match.group(0)
        if mentioned == expected:
            return match.group(0)
        findings.append(
            StructuralFinding(
                "time_error",
                "E1",
                5,
                match.group(0),
                "相对日期必须与此刻一致",
                "clock:" + today.isoformat(),
                f"核对为{expected.month}月{expected.day}日",
            )
        )
        note = "" if context.critic_available else f"（日期以 {expected.month}月{expected.day}日 为准）"
        return match.group(0) if note and text[match.end() :].startswith(note) else match.group(0) + note

    return RELATIVE_PATTERN.sub(substitute, text), findings

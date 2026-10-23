"""Deterministic civil calendar arithmetic, using explicit time and existing P2 calendar data."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from lunar_python import Solar

from mingjing_core.agent.tools.date_parameters import DateCalc
from mingjing_core.timeparse.calendar_port import P2CalendarPort


def civil_date(value: str, zone: str) -> date:
    if len(value) == 10 and date.fromisoformat(value).isoformat() == value:
        return date.fromisoformat(value)
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("日期时间必须带时区")
    return instant.astimezone(ZoneInfo(zone)).date()


def add_date(start: date, number: int, unit: str) -> tuple[date, str]:
    if unit in {"day", "week"}:
        return start + timedelta(
            days=number * (7 if unit == "week" else 1)
        ), "按公历日加减"
    months = number * (12 if unit == "year" else 1)
    year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
    day = min(start.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day), "按公历月份加减；超出目标月份的日期取月末"


def full_months(start: date, end: date) -> int:
    if end < start:
        return -full_months(end, start)
    return (
        (end.year - start.year) * 12 + end.month - start.month - (end.day < start.day)
    )


def difference(
    start: date, end: date, unit: str, inclusive: bool
) -> tuple[dict[str, Any], str]:
    raw_days = (end - start).days
    days = raw_days + ((1 if raw_days >= 0 else -1) if inclusive else 0)
    weeks = (abs(days) // 7) * (1 if days >= 0 else -1)
    months = full_months(start, end)
    years = (abs(months) // 12) * (1 if months >= 0 else -1)
    result = {
        "days": days,
        "weeks": weeks,
        "value": {"day": days, "week": weeks, "month": months, "year": years}[unit],
        "unit": unit,
        "inclusive": inclusive,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    method = (
        "终点减起点；日/周首尾均计入"
        if inclusive
        else "终点减起点，不额外加一天；月/年取完整日历单位"
    )
    return result, method


def lunar_date(value: date) -> dict[str, Any]:
    if not 1900 <= value.year <= 2200:
        raise ValueError("历法年份须在1900至2200之间")
    lunar = Solar.fromYmd(value.year, value.month, value.day).getLunar()
    return {
        "year": lunar.getYear(),
        "month": abs(lunar.getMonth()),
        "day": lunar.getDay(),
        "leap_month": lunar.getMonth() < 0,
    }


def age(birth: date, reference: date) -> tuple[dict[str, Any], str]:
    if reference < birth:
        raise ValueError("年龄参照日不能早于出生日期")
    completed = (
        reference.year
        - birth.year
        - ((reference.month, reference.day) < (birth.month, birth.day))
    )
    traditional = lunar_date(reference)["year"] - lunar_date(birth)["year"] + 1
    method = "周岁按公历生日；虚岁出生计一岁，农历春节加一岁（传统口径之一）"
    return {
        "周岁": completed,
        "虚岁": traditional,
        "reference_date": reference.isoformat(),
    }, method


def convert_lunar(value: str) -> tuple[dict[str, Any], str]:
    match = re.fullmatch(r"农历(\d{4})-(闰)?(\d{2})-(\d{2})", value)
    if match is None:
        raise ValueError("农历日期需为农历YYYY-MM-DD，闰月在月份前写闰")
    year, leap, month, day = match.groups()
    converted = P2CalendarPort().lunar_date(int(year), int(month), int(day), bool(leap))
    return {
        "date": converted.isoformat(),
        "weekday": converted.isoweekday(),
        "leap_month": bool(leap),
    }, "复用P2已锁定农历库；非法农历日或不存在的闰月不顺延"


def calculate(args: DateCalc, reference: datetime | None, zone: str) -> dict[str, Any]:
    ZoneInfo(zone)
    if args.op == "lunar_to_solar":
        result, method = convert_lunar(args.a)
    else:
        start = civil_date(args.a, zone)
        result, method = _civil(args, start, reference, zone)
    return {"result": result, "explanation": method, "method": method}


def _civil(
    args: DateCalc, start: date, reference: datetime | None, zone: str
) -> tuple[dict[str, Any], str]:
    if args.op == "diff":
        return difference(
            start, civil_date(args.b, zone), args.unit or "day", args.inclusive
        )
    if args.op == "add":
        end, method = add_date(start, args.n, args.unit or "day")
        return {"date": end.isoformat(), "weekday": end.isoweekday()}, method
    if args.op == "age":
        if args.b:
            at = civil_date(args.b, zone)
        else:
            if (
                reference is None
                or reference.tzinfo is None
                or reference.utcoffset() is None
            ):
                raise ValueError("默认年龄参照日需要程序提供带时区的此刻")
            at = reference.astimezone(ZoneInfo(zone)).date()
        return age(start, at)
    if args.op == "weekday":
        return {
            "date": start.isoformat(),
            "weekday": start.isoweekday(),
        }, "ISO星期：周一为1，周日为7"
    if args.op == "solar_to_lunar":
        return lunar_date(start), "复用P2已锁定农历库；闰月单独标记"
    raise ValueError("不支持的日期操作")

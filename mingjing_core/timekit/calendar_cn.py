"""Offline Chinese holiday arrangements; unpublished years never imply leave."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from lunar_python import Lunar, Solar
from lunar_python.util import HolidayUtil

HOLIDAY_DIR = Path(__file__).resolve().parents[2] / "config" / "holidays"
BUILTIN_MAX_YEAR = 2026  # lunar-python 1.4.8's published arrangement horizon.


@dataclass(frozen=True)
class DayStatus:
    kind: Literal["workday", "weekend", "holiday", "adjusted_workday"]
    holiday_name: str | None
    is_off: bool
    source: Literal["builtin", "override", "unpublished"]


@dataclass(frozen=True)
class Holiday:
    name: str
    date: date
    days_to: int
    arrangement_published: bool


def validate_holidays(value: object) -> dict:
    if not isinstance(value, dict) or type(value.get("year")) is not int:
        raise ValueError("节假日文件需要整数 year")
    if not 1900 <= value["year"] <= 2200 or not isinstance(value.get("days"), list):
        raise ValueError("节假日年份或 days 无效")
    if not isinstance(value.get("papers", []), list) or any(
        not isinstance(paper, str) for paper in value.get("papers", [])
    ):
        raise ValueError("节假日来源 papers 必须是字符串列表")
    seen = set()
    for item in value["days"]:
        if not isinstance(item, dict) or set(item) != {"name", "date", "isOffDay"}:
            raise ValueError("节假日条目只接受 name/date/isOffDay")
        parsed = date.fromisoformat(item["date"])
        if parsed.year != value["year"] or parsed in seen or type(item["isOffDay"]) is not bool:
            raise ValueError("节假日日期重复、年份不符或休息标志无效")
        if not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 80:
            raise ValueError("节假日名称无效")
        seen.add(parsed)
    return value


def arrangement(year: int, directory: Path | None = None) -> dict | None:
    path = (directory or HOLIDAY_DIR) / f"{year}.json"
    if not path.exists():
        return None
    value = validate_holidays(json.loads(path.read_text(encoding="utf-8")))
    if value["year"] != year:
        raise ValueError("节假日文件名与年份不一致")
    return value


def day_status(day: date, *, directory: Path | None = None) -> DayStatus:
    override = arrangement(day.year, directory)
    source = "override" if override is not None else "builtin" if day.year <= BUILTIN_MAX_YEAR else "unpublished"
    if override is not None:
        item = next((item for item in override["days"] if item["date"] == day.isoformat()), None)
        if item:
            return DayStatus(
                "holiday" if item["isOffDay"] else "adjusted_workday", item["name"], item["isOffDay"], source
            )
    elif source == "builtin":
        item = HolidayUtil.getHoliday(day.isoformat())
        if item:
            return DayStatus(
                "adjusted_workday" if item.isWork() else "holiday", item.getName(), not item.isWork(), source
            )
    weekend = day.weekday() >= 5
    return DayStatus("weekend" if weekend else "workday", None, weekend, source)


def statutory_dates(year: int) -> list[tuple[date, str]]:
    values = [(date(year, 1, 1), "元旦"), (date(year, 5, 1), "劳动节"), (date(year, 10, 1), "国庆节")]
    for month, day, name in ((1, 1, "春节"), (5, 5, "端午节"), (8, 15, "中秋节")):
        solar = Lunar.fromYmd(year, month, day).getSolar()
        values.append((date(solar.getYear(), solar.getMonth(), solar.getDay()), name))
    qingming = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()["清明"]
    values.append((date(qingming.getYear(), qingming.getMonth(), qingming.getDay()), "清明节"))
    return sorted(values)


def next_holiday(from_date: date, *, directory: Path | None = None) -> Holiday:
    candidates = []
    for year in (from_date.year, from_date.year + 1):
        published = arrangement(year, directory) is not None or year <= BUILTIN_MAX_YEAR
        if published:
            day = max(from_date, date(year, 1, 1))
            while day.year == year:
                status = day_status(day, directory=directory)
                if status.kind == "holiday":
                    candidates.append(Holiday(status.holiday_name or "法定假日", day, (day - from_date).days, True))
                    break
                day += timedelta(days=1)
        else:
            candidates.extend(
                Holiday(name, day, (day - from_date).days, False)
                for day, name in statutory_dates(year)
                if day >= from_date
            )
    if not candidates:
        raise ValueError("无法确定下一法定节日")
    return min(candidates, key=lambda item: item.date)


def holiday_window(day: date, *, directory: Path | None = None) -> tuple[date, date] | None:
    status = day_status(day, directory=directory)
    if status.kind != "holiday":
        return None
    start = end = day
    for direction in (-1, 1):
        cursor = day
        for _ in range(20):
            candidate = cursor + timedelta(days=direction)
            other = day_status(candidate, directory=directory)
            if other.kind != "holiday" or other.holiday_name != status.holiday_name:
                break
            cursor = candidate
        if direction == -1:
            start = cursor
        else:
            end = cursor
    return start, end

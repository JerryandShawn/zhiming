"""Read-only bridge to P2's calendar engine; no copied holiday arrangements or downloads."""

from datetime import date, datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from lunar_python import Lunar, LunarYear, Solar

from mingjing_core.timekit import calendar_cn
from mingjing_core.timekit.almanac import solar_instant
from mingjing_core.timekit.calendar_cn import DayStatus


class CalendarPort(Protocol):
    def day_status(self, day: date) -> DayStatus:
        """P2 source='unpublished' is not authority for adjusted workdays."""
        ...

    def statutory_dates(self, year: int) -> list[tuple[date, str]]:
        """Known festival dates, separately from published leave arrangements."""
        ...

    def holiday_window(self, day: date) -> tuple[date, date] | None:
        """P2 window with inclusive calendar dates, if published."""
        ...

    def lunar_date(self, year: int, month: int, day: int, leap: bool = False) -> date:
        """Convert an explicitly identified Chinese lunar date."""
        ...

    def solar_term(self, year: int, name: str, tz: str = "Asia/Shanghai") -> datetime:
        """Physical instant from P2's pinned lunar library and civil-time conversion."""
        ...


class P2CalendarPort:
    def __init__(self, *, directory: Path | None = None) -> None:
        self.directory = directory

    def day_status(self, day: date) -> DayStatus:
        return calendar_cn.day_status(day, directory=self.directory)

    def statutory_dates(self, year: int) -> list[tuple[date, str]]:
        _year(year)
        return calendar_cn.statutory_dates(year)

    def holiday_window(self, day: date) -> tuple[date, date] | None:
        if self.day_status(day).source == "unpublished":
            return None
        return calendar_cn.holiday_window(day, directory=self.directory)

    def lunar_date(self, year: int, month: int, day: int, leap: bool = False) -> date:
        _year(year)
        if (
            type(month) is not int
            or type(day) is not int
            or type(leap) is not bool
            or not 1 <= month <= 12
            or not 1 <= day <= 30
        ):
            raise ValueError("农历日期无效")
        lunar_month = LunarYear.fromYear(year).getMonth(-month if leap else month)
        if lunar_month is None or day > lunar_month.getDayCount():
            raise ValueError("该年不存在所指定的农历月份或日期")
        solar = Lunar.fromYmd(year, -month if leap else month, day).getSolar()
        return date(solar.getYear(), solar.getMonth(), solar.getDay())

    def solar_term(self, year: int, name: str, tz: str = "Asia/Shanghai") -> datetime:
        _year(year)
        if name not in Lunar.JIE_QI:
            raise ValueError("节气名称无效")
        table = Solar.fromYmd(year, 6, 1).getLunar().getJieQiTable()
        # The table spans adjacent years and uses Latin keys at its ends. Index by
        # the library's public name cycle, then require the requested Gregorian year.
        aliases = {key: Lunar.JIE_QI[(index - 1) % 24] for index, key in enumerate(Lunar.JIE_QI_IN_USE)}
        matches = [solar for key, solar in table.items() if aliases.get(key, key) == name and solar.getYear() == year]
        if len(matches) != 1:
            raise ValueError("无法唯一确定该年的节气时刻")
        return solar_instant(matches[0], ZoneInfo(tz))


def _year(year: int) -> None:
    if type(year) is not int or not 1900 <= year <= 2200:
        raise ValueError("历法年份须在1900至2200之间")

"""Deterministic calendar facts from the pinned lunar-python calculation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from lunar_python import Solar

PERIODS = ((5, "凌晨"), (8, "早上"), (11, "上午"), (13, "中午"), (17, "下午"), (19, "傍晚"), (23, "晚上"), (24, "深夜"))


@dataclass(frozen=True)
class Almanac:
    solar: str
    weekday: str
    period: str
    lunar: dict
    ganzhi: dict
    jieqi: dict
    festivals: list[str]
    yi: list[str]
    ji: list[str]
    chong: str
    sha: str
    xiu: str
    zhixing: str
    zi_hour_note: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def solar_instant(solar: Solar, zone: ZoneInfo) -> datetime:
    # This library's astronomical term times are China civil time, independent
    # of the owner's display zone. Converting once avoids shifting the instant.
    value = datetime.fromisoformat(solar.toYmdHms()).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return value.astimezone(zone)


def almanac(dt: datetime, tz: str | ZoneInfo = "Asia/Shanghai") -> Almanac:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("历法计算需要带时区的时刻")
    zone = ZoneInfo(tz) if isinstance(tz, str) else tz
    local = dt.astimezone(zone)
    solar = Solar.fromYmdHms(local.year, local.month, local.day, local.hour, local.minute, local.second)
    lunar = solar.getLunar()
    # Term selection follows physical instants, rather than a whole term day.
    physical = Solar.fromYmdHms(*(dt.astimezone(ZoneInfo("Asia/Shanghai")).timetuple()[:6])).getLunar()
    previous_term, following_term = physical.getPrevJieQi(), physical.getNextJieQi()
    previous = solar_instant(previous_term.getSolar(), zone), previous_term.getName()
    following = solar_instant(following_term.getSolar(), zone), following_term.getName()
    return Almanac(
        solar=local.date().isoformat(),
        weekday="星期" + "一二三四五六日"[local.weekday()],
        period=next(label for end, label in PERIODS if local.hour < end),
        lunar={
            "year": lunar.getYearInGanZhi(),
            "zodiac": lunar.getYearShengXiao(),
            "month": lunar.getMonthInChinese(),
            "day": lunar.getDayInChinese(),
            "is_leap": lunar.getMonth() < 0,
        },
        ganzhi={
            "year": physical.getYearInGanZhiExact(),
            "month": physical.getMonthInGanZhiExact(),
            "day": lunar.getDayInGanZhi(),
            "hour": lunar.getTimeInGanZhi(),
        },
        jieqi={
            "current": previous[1],
            "current_at": previous[0].isoformat(),
            "next": following[1],
            "next_at": following[0].isoformat(),
            "days_to_next": (following[0].date() - local.date()).days,
        },
        festivals=list(dict.fromkeys(solar.getFestivals() + lunar.getFestivals() + lunar.getOtherFestivals())),
        yi=lunar.getDayYi(),
        ji=lunar.getDayJi(),
        chong=lunar.getDayChongDesc(),
        sha=lunar.getDaySha(),
        xiu=lunar.getXiu(),
        zhixing=lunar.getZhiXing(),
        zi_hour_note="lunar-python 默认晚子时不换日；部分流派此时已换日。" if local.hour == 23 else None,
    )


def term_display(value: str) -> str:
    rounded = datetime.fromisoformat(value) + timedelta(seconds=30)
    return f"{rounded.month}月{rounded.day}日 {rounded:%H:%M}"

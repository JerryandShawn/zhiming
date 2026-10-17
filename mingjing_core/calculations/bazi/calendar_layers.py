"""Calendar layers preserve the existing sects and explicit UTC+8 convention."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import isfinite
from typing import Any

from .elements import HIDDEN, block, relative_pillar, table, ten_god

JIE = ("立春", "惊蛰", "清明", "立夏", "芒种", "小暑", "立秋", "白露", "寒露", "立冬", "大雪", "XIAO_HAN", "LI_CHUN")


def solar_at(engine: Any, value: datetime) -> Any:
    return engine.Solar.fromYmdHms(value.year, value.month, value.day, value.hour, value.minute, value.second)


def iso(solar: Any) -> str:
    return solar.toYmdHms().replace(" ", "T") + "+08:00"


def command_at(month: str, elapsed_days: float, master: str) -> dict[str, Any]:
    if isinstance(elapsed_days, bool) or not isfinite(elapsed_days) or elapsed_days < 0:
        raise ValueError("节后经过日数必须为有限非负数")
    rules = table("month_command")
    elapsed, start = float(elapsed_days), 0
    schedule = rules["schedules"][month]
    selected = len(schedule) - 1
    for index, (_, duration) in enumerate(schedule):
        if elapsed < start + duration:
            selected = index
            break
        start += duration
    stem = schedule[selected][0]
    return block(
        rules["method"],
        rules["source"],
        table_version=rules["version"],
        month_branch=month,
        elapsed_days=round(elapsed, 9),
        schedule=[{"stem": stem, "days": days} for stem, days in schedule],
        selected_segment=selected,
        commanding_stem=stem,
        ten_god=ten_god(master, stem),
        also_in_v3_hidden_stems=stem in HIDDEN[month],
        elapsed_rule=rules["elapsed_rule"],
        warnings=[rules["source_normalization"], "该表不同于常见7/7/16表；不覆盖v3本气字段；分日法待大脑定稿"],
    )


def month_command(engine: Any, calendar: datetime, month: str, master: str) -> dict[str, Any]:
    lunar = solar_at(engine, calendar).getLunar()
    previous, following = lunar.getPrevJie(), lunar.getNextJie()
    boundary = datetime.fromisoformat(previous.getSolar().toYmdHms())
    value = command_at(month, (calendar - boundary).total_seconds() / 86400, master)
    value.update(
        {
            "calendar_birth_at": calendar.isoformat() + "+08:00",
            "period_start": iso(previous.getSolar()),
            "period_end_exclusive": iso(following.getSolar()),
            "start_jie": previous.getName(),
        }
    )
    return value


def decade_luck(engine: Any, calendar: datetime, gender: int, pillars: dict[str, str]) -> dict[str, Any]:
    eight = solar_at(engine, calendar).getLunar().getEightChar()
    eight.setSect(2)
    yun = eight.getYun(gender, 1)
    start = yun.getStartSolar()
    rows = []
    for index, row in enumerate(yun.getDaYun(11)[1:]):
        rows.append(
            {
                "index": index + 1,
                **relative_pillar(row.getGanZhi(), pillars["day"][0], pillars),
                "nominal_start_at": iso(start.nextYear(index * 10)),
                "nominal_end_exclusive": iso(start.nextYear((index + 1) * 10)),
                "legacy_start_age": row.getStartAge(),
                "legacy_end_age": row.getEndAge(),
                "legacy_start_year": row.getStartYear(),
                "legacy_end_year": row.getEndYear(),
            }
        )
    return block(
        "p8-lunar-python-yun-sect1-v1",
        "lunar-python1.4.8 Yun/DaYun，沿用v3 getYun(gender,1)",
        forward=yun.isForward(),
        start_age={
            "years": yun.getStartYear(),
            "months": yun.getStartMonth(),
            "days": yun.getStartDay(),
            "hours": yun.getStartHour(),
        },
        nominal_start_at=iso(start),
        decades=rows,
        precision="sect1时辰折算后日历时间；不是天文精确应期；十年边界为项目按起运日历年递增",
        warning="旧按年份/虚岁显示与新增日历交运日分开保存；不改变旧结果；闰日nextYear遵从锁定库",
    )


def calendar_layers(engine: Any, year: int, target_date: str, pillars: dict[str, str]) -> dict[str, Any]:
    master = pillars["day"][0]
    jie = engine.Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
    months = []
    for index, (left, right) in enumerate(zip(JIE[:-1], JIE[1:], strict=True)):
        start, end = jie[left], jie[right]
        # One second inside the exact boundary avoids asking a minute engine to
        # silently truncate a second-level Jie boundary onto the prior month.
        sample = datetime.fromisoformat(start.toYmdHms()) + timedelta(seconds=1)
        month = solar_at(engine, sample).getLunar().getMonthInGanZhiExact()
        months.append(
            {
                "index": index + 1,
                **relative_pillar(month, master, pillars),
                "period_start": iso(start),
                "period_end_exclusive": iso(end),
                "sample_at": sample.isoformat() + "+08:00",
                "start_jie": left,
            }
        )
    annual = engine.Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getYearInGanZhiExact()
    snapshot = datetime.strptime(target_date, "%Y-%m-%d").replace(hour=12)
    lunar = solar_at(engine, snapshot).getLunar()
    daily = {
        "date": target_date,
        "sample_at": snapshot.isoformat() + "+08:00",
        "year": relative_pillar(lunar.getYearInGanZhiExact(), master, pillars),
        "month": relative_pillar(lunar.getMonthInGanZhiExact(), master, pillars),
        "day": relative_pillar(lunar.getDayInGanZhiExact2(), master, pillars),
        "hour": relative_pillar(lunar.getTimeInGanZhi(), master, pillars),
        "hour_is_snapshot_only": True,
        "period_start": iso(lunar.getPrevJie().getSolar()),
        "period_end_exclusive": iso(lunar.getNextJie().getSolar()),
    }
    return block(
        "p8-exact-jie-year-month-and-noon-day-sect2-v1",
        "lunar-python1.4.8；复用v3节界与目标日UTC+8正午",
        requested_gregorian_year=year,
        year={
            **relative_pillar(annual, master, pillars),
            "period_start": iso(jie["立春"]),
            "period_end_exclusive": iso(jie["LI_CHUN"]),
        },
        months=months,
        day=daily,
        warning="十二节月覆盖该年立春至次年立春；目标日可在另一节年；时柱仅正午快照，不代表整日择时",
    )

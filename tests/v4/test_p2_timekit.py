"""Published calendar examples and unknown-year boundaries are observable contracts."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timekit.almanac import almanac
from mingjing_core.timekit.calendar_cn import (
    day_status,
    next_holiday,
    validate_holidays,
)
from mingjing_core.timekit.clock import FrozenClock
from mingjing_core.timekit.now_block import render_now_block
from tools.update_holidays import update

if TYPE_CHECKING:
    from pathlib import Path

SHANGHAI = ZoneInfo("Asia/Shanghai")


@pytest.mark.parametrize(
    "day,weekday,lunar,day_pillar,kind",
    [
        ("2026-02-14", "六", "腊月廿七", "己未", "adjusted_workday"),
        ("2026-02-17", "二", "正月初一", "壬戌", "holiday"),
        ("2026-05-09", "六", "三月廿三", "癸未", "adjusted_workday"),
        ("2026-09-20", "日", "八月初十", "丁酉", "adjusted_workday"),
        ("2026-10-05", "一", "八月廿五", "壬子", "holiday"),
        ("2026-10-10", "六", "九月初一", "丁巳", "adjusted_workday"),
        ("2026-10-17", "六", "九月初八", "甲子", "weekend"),
        ("2026-10-18", "日", "九月初九", None, "weekend"),
        ("2026-10-21", "三", "九月十二", "戊辰", "workday"),
        ("2026-11-07", "六", "九月廿九", "乙酉", "weekend"),
        ("2026-12-22", "二", "冬月十四", "庚午", "workday"),
        ("2027-01-01", "五", "冬月廿四", None, "workday"),
        ("2027-02-06", "六", "正月初一", None, "weekend"),
    ],
)
def test_calendar_appendix(day: str, weekday: str, lunar: str, day_pillar: str | None, kind: str) -> None:
    value = almanac(datetime.fromisoformat(day + "T10:30:00+08:00"))
    assert value.weekday == "星期" + weekday
    assert value.lunar["month"] + "月" + value.lunar["day"] == lunar
    if day_pillar:
        assert value.ganzhi["day"] == day_pillar
    assert day_status(date.fromisoformat(day)).kind == kind


def test_now_block_matches_all_blueprint_fields_and_real_arrangements() -> None:
    clock = FrozenClock(datetime(2026, 10, 17, 10, 30, tzinfo=SHANGHAI))
    text = render_now_block(
        {},
        clock,
        {"at": "2026-10-15T21:05:00+08:00", "channel": "飞书"},
        [{"id": "f31", "event_at": "2026-10-21", "title": "面试"}],
    )
    for fragment in (
        "2026年10月17日 星期六 上午 10:30",
        "丙午年（马年）九月初八",
        "丙午年 戊戌月 甲子日 己巳时",
        "寒露（10月8日 14:29",
        "霜降，10月23日 17:38",
        "还有 6 天",
        "明天 10月18日",
        "重阳节",
        "非法定放假",
        "2027年1月1日",
        "还有 76 天",
        "尚未公布",
        "10月10日（周六）为调休上班日",
        "距上次对话：2 天",
        "10月21日（周三）面试〔f31〕",
        "黄历：宜",
        "；忌",
        "煞南",
    ):
        assert fragment in text


def test_late_zi_uses_documented_day_and_hour_without_greeting_error() -> None:
    value = almanac(datetime(2026, 10, 17, 23, 30, tzinfo=SHANGHAI))
    assert value.lunar["day"] == "初八"
    assert value.ganzhi["day"] == "甲子" and value.ganzhi["hour"] == "丙子"
    assert value.period == "深夜" and "部分流派" in value.zi_hour_note


@pytest.mark.parametrize("day,name", [(date(2027, 1, 1), "元旦"), (date(2027, 2, 6), "春节")])
def test_unpublished_year_only_claims_festival_date(day: date, name: str) -> None:
    assert day_status(day).source == "unpublished"
    holiday = next_holiday(day)
    assert holiday.name == name and holiday.date == day
    assert holiday.arrangement_published is False


@pytest.mark.parametrize("instant,name", [("2026-10-23T17:37:57+08:00", "霜降"), ("2026-11-07T17:52:05+08:00", "立冬")])
def test_term_changes_at_the_calculated_second(instant: str, name: str) -> None:
    at = datetime.fromisoformat(instant)
    assert almanac(at - timedelta(seconds=1)).jieqi["next"] == name
    assert almanac(at + timedelta(seconds=1)).jieqi["current"] == name
    # The same physical term is displayed in the owner's timezone once.
    assert almanac(at + timedelta(seconds=1), "UTC").jieqi["current"] == name


def test_clock_zone_changes_civil_day_and_keeps_term_instant() -> None:
    clock = FrozenClock(datetime.fromisoformat("2026-10-17T23:30:00+00:00"))
    text = render_now_block({"timezone": "Asia/Shanghai"}, clock)
    assert "2026年10月18日 星期日" in text
    assert "今天 10月18日" in text and "重阳节" in text


def test_holiday_override_validated_diff_and_idempotent_update(tmp_path: Path) -> None:
    value = {
        "year": 2027,
        "papers": ["self-hosted-test"],
        "days": [{"date": "2027-01-02", "name": "合成调休", "isOffDay": False}],
    }
    source = tmp_path / "input.json"
    source.write_text(json.dumps(value), encoding="utf-8")
    output = tmp_path / "holidays"
    assert update(str(source), output)["changed_dates"] == ["2027-01-02"]
    assert update(str(source), output)["changed_dates"] == []
    assert day_status(date(2027, 1, 2), directory=output).kind == "adjusted_workday"
    assert day_status(date(2027, 1, 1), directory=output).source == "override"
    with pytest.raises(ValueError):
        validate_holidays(dict(value, days=value["days"] * 2))


def test_new_year_terms_have_chinese_names_and_naive_time_is_rejected() -> None:
    assert almanac(datetime(2027, 1, 1, tzinfo=SHANGHAI)).jieqi["current"] == "冬至"
    with pytest.raises(ValueError):
        almanac(datetime(2026, 10, 17))


@pytest.mark.parametrize("zone", ["Asia/Shanghai", "America/New_York"])
@pytest.mark.parametrize(
    "instant,year,month",
    [
        ("2026-02-04T04:02:07+08:00", "乙巳", "己丑"),
        ("2026-02-04T04:02:09+08:00", "丙午", "庚寅"),
    ],
)
def test_year_and_month_pillars_follow_same_physical_lichun_instant_in_each_zone(
    zone: str, instant: str, year: str, month: str
) -> None:
    value = almanac(datetime.fromisoformat(instant), zone)
    assert value.ganzhi["year"] == year
    assert value.ganzhi["month"] == month
    assert (value.jieqi["current"] == "立春") == (year == "丙午")

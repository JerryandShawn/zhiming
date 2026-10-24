"""The supplied original instant, not the OS date, determines relative dates."""

from __future__ import annotations

from datetime import datetime

import pytest

from mingjing_core.application.time_range_parser import ModuleTimeRangeParser

AT = datetime.fromisoformat("2026-10-17T10:30:00+08:00")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("今天面试", "2026-10-17"),
        ("明天面试", "2026-10-18"),
        ("后天面试", "2026-10-19"),
        ("大后天面试", "2026-10-20"),
        ("昨天面试", "2026-10-16"),
        ("前天面试", "2026-10-15"),
        ("大前天面试", "2026-10-14"),
        ("下周三面试", "2026-10-21"),
        ("下下周一面试", "2026-10-26"),
        ("本周五面试", "2026-10-16"),
        ("上周三面试", "2026-10-07"),
        ("三天后面试", "2026-10-20"),
        ("两天前面试", "2026-10-15"),
        ("一周后面试", "2026-10-24"),
        ("2026-10-21面试", "2026-10-21"),
    ],
)
def test_concrete_event_day(text: str, expected: str) -> None:
    result = ModuleTimeRangeParser().resolve(text, said_at=AT, timezone="Asia/Shanghai")
    assert result.status == "resolved" and result.event_at == expected
    assert result.expression and result.expression in text


@pytest.mark.parametrize(
    "text",
    [
        "我喜欢读书",
        "这是后天形成的习惯",
        "三方四正",
        "没有日期的记录",
        "时间管理课",
    ],
)
def test_non_time_is_not_fabricated(text: str) -> None:
    result = ModuleTimeRangeParser().resolve(text, said_at=AT, timezone="Asia/Shanghai")
    assert result.status == "not_date" and result.event_at is None


@pytest.mark.parametrize(
    "text",
    [
        "月底面试",
        "每周三面试",
        "明天或后天面试",
        "明天和后天各有面试",
        "过几天面试",
        "2026-02-30面试",
        "下学期开学",
        "今晚凌晨面试",
    ],
)
def test_ranges_or_ambiguity_never_become_a_single_confirmed_day(text: str) -> None:
    result = ModuleTimeRangeParser().resolve(text, said_at=AT, timezone="Asia/Shanghai")
    assert result.status == "needs_confirmation" and result.event_at is None


def test_range_adapter_keeps_half_open_bounds_without_claiming_an_event_day() -> None:
    result = ModuleTimeRangeParser().parse_time_range("下个月", AT)
    assert result.kind == "range" and not result.needs_clarification
    assert result.start.isoformat() == "2026-10-31T16:00:00+00:00"
    assert result.end.isoformat() == "2026-11-30T16:00:00+00:00"


@pytest.mark.parametrize("system_zone", ["Asia/Tokyo", "UTC", "America/New_York"])
def test_owner_zone_wins_over_host_zone(
    system_zone: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", system_zone)
    at = datetime.fromisoformat("2026-12-31T23:30:00+00:00")
    parser = ModuleTimeRangeParser()
    assert (
        parser.resolve("明天", said_at=at, timezone="Asia/Shanghai").event_at
        == "2027-01-02"
    )
    assert (
        parser.resolve("明天", said_at=at, timezone="America/New_York").event_at
        == "2027-01-01"
    )


def test_naive_reference_is_rejected() -> None:
    with pytest.raises(ValueError):
        ModuleTimeRangeParser().resolve(
            "明天", said_at=datetime(2026, 10, 17), timezone="Asia/Shanghai"
        )

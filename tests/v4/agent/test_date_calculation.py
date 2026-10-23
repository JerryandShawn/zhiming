"""Original P3 date operations have explicit, deterministic calendar methods."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from mingjing_core.agent.prompts import load_prompts
from mingjing_core.agent.tools.computation_definitions import computation_definitions
from mingjing_core.agent.tools.date_parameters import DateCalc
from mingjing_core.application.agent_tools_computation import date_calc
from mingjing_core.domain.contracts import EvidenceError


@pytest.mark.parametrize(
    "start,number,unit,expected",
    [
        ("2026-10-17", 4, "day", "2026-10-21"),
        ("2026-12-31", 1, "day", "2027-01-01"),
        ("2024-02-28", 1, "day", "2024-02-29"),
        ("2025-02-28", 1, "day", "2025-03-01"),
        ("2026-01-01", -1, "day", "2025-12-31"),
        ("2026-10-17", 2, "week", "2026-10-31"),
        ("2026-10-17", -1, "week", "2026-10-10"),
        ("2026-01-31", 1, "month", "2026-02-28"),
        ("2024-01-31", 1, "month", "2024-02-29"),
        ("2026-03-31", -1, "month", "2026-02-28"),
        ("2026-12-31", 1, "month", "2027-01-31"),
        ("2024-02-29", 1, "year", "2025-02-28"),
        ("2024-02-29", 4, "year", "2028-02-29"),
    ],
)
def test_addition(start: str, number: int, unit: str, expected: str) -> None:
    result = date_calc({"op": "add", "a": start, "n": number, "unit": unit})
    assert result.ok and result.data["result"]["date"] == expected
    assert result.summary == "算了一下日期" and result.receipt is None
    assert result.data["method"]
    if unit in {"month", "year"}:
        assert "月末" in result.data["method"]


@pytest.mark.parametrize(
    "start,end,inclusive,days",
    [
        ("2026-10-17", "2026-10-21", False, 4),
        ("2026-10-17", "2026-10-21", True, 5),
        ("2026-10-21", "2026-10-17", False, -4),
        ("2026-10-21", "2026-10-17", True, -5),
        ("2026-10-17", "2026-10-17", False, 0),
        ("2026-10-17", "2026-10-17", True, 1),
        ("2024-02-28", "2024-03-01", False, 2),
        ("2025-02-28", "2025-03-01", False, 1),
    ],
)
def test_difference(start: str, end: str, inclusive: bool, days: int) -> None:
    result = date_calc({"op": "diff", "a": start, "b": end, "inclusive": inclusive})
    assert (
        result.data["result"]["days"] == days and result.data["result"]["value"] == days
    )


@pytest.mark.parametrize(
    "args,value",
    [
        ({"a": "2026-10-01", "b": "2026-10-15", "unit": "week"}, 2),
        ({"a": "2026-01-31", "b": "2026-02-28", "unit": "month"}, 0),
        ({"a": "2026-01-31", "b": "2026-03-31", "unit": "month"}, 2),
        ({"a": "2026-03-31", "b": "2026-01-31", "unit": "month"}, -2),
        ({"a": "2020-10-17", "b": "2026-10-16", "unit": "year"}, 5),
    ],
)
def test_difference_units(args: dict, value: int) -> None:
    assert date_calc({"op": "diff", **args}).data["result"]["value"] == value


@pytest.mark.parametrize(
    "birth,reference,completed,traditional",
    [
        ("1994-10-18", "2026-10-17", 31, 33),
        ("1994-10-17", "2026-10-17", 32, 33),
        ("2025-01-28", "2025-01-29", 0, 2),
        ("2025-01-29", "2026-02-16", 1, 1),
        ("2025-01-29", "2026-02-17", 1, 2),
    ],
)
def test_age_around_birthdays_and_lunar_new_year(
    birth: str, reference: str, completed: int, traditional: int
) -> None:
    data = date_calc({"op": "age", "a": birth, "b": reference}).data
    assert data["result"]["周岁"] == completed and data["result"]["虚岁"] == traditional
    assert "农历春节" in data["method"]


def test_default_age_reference_is_explicit_program_clock_in_owner_zone() -> None:
    at = datetime.fromisoformat("2026-10-16T16:30:00+00:00")
    result = date_calc(
        {"op": "age", "a": "1994-10-17"}, ref_time=at, timezone="Asia/Shanghai"
    )
    assert result.data["result"]["周岁"] == 32
    with pytest.raises(EvidenceError):
        date_calc({"op": "age", "a": "1994-10-17"})


@pytest.mark.parametrize(
    "raw,expected",
    [("2026-10-17", 6), ("2026-10-21", 3), ("2026-10-16T16:30:00Z", 6)],
)
def test_weekday_and_explicit_iso_in_owner_zone(raw: str, expected: int) -> None:
    assert date_calc({"op": "weekday", "a": raw}).data["result"]["weekday"] == expected


@pytest.mark.parametrize(
    "lunar,solar",
    [
        ("农历2026-01-01", "2026-02-17"),
        ("农历2025-闰06-01", "2025-07-25"),
        ("农历2025-06-01", "2025-06-25"),
    ],
)
def test_valid_lunar_conversions(lunar: str, solar: str) -> None:
    result = date_calc({"op": "lunar_to_solar", "a": lunar})
    assert result.data["result"]["date"] == solar
    reverse = date_calc({"op": "solar_to_lunar", "a": solar}).data["result"]
    assert reverse["leap_month"] == ("闰" in lunar)
    assert reverse["day"] == 1


@pytest.mark.parametrize(
    "args",
    [
        {"op": "weekday", "a": "下周三"},
        {"op": "weekday", "a": "2026-10-17T10:30:00"},
        {"op": "weekday", "a": "2026-02-30"},
        {"op": "age", "a": "2027-01-01", "b": "2026-10-17"},
        {"op": "lunar_to_solar", "a": "农历2026-闰06-01"},
        {"op": "lunar_to_solar", "a": "农历2026-01-31"},
        {"op": "solar_to_lunar", "a": "1800-01-01"},
        {"op": "add", "a": "9999-12-31", "n": 1},
        {"op": "add", "a": "2026-01-01", "n": 36600, "unit": "year"},
    ],
)
def test_invalid_calendars_do_not_guess_or_roll_over(args: dict) -> None:
    with pytest.raises(EvidenceError):
        date_calc(args)


@pytest.mark.parametrize(
    "args",
    [
        {"op": "diff", "a": "2026-10-17"},
        {"op": "add", "a": "2026-10-17", "n": True},
        {"op": "add", "a": "2026-10-17", "n": 1.5},
        {"op": "add", "a": "2026-10-17", "n": 1, "b": "2026-10-18"},
        {"op": "weekday", "a": "2026-10-17", "n": 1},
        {"op": "weekday", "a": "2026-10-17", "owner": "other"},
        {"op": "weekday", "a": "2026-10-17", "timezone": "Asia/Tokyo"},
        {
            "op": "diff",
            "a": "2026-10-17",
            "b": "2027-10-17",
            "unit": "year",
            "inclusive": True,
        },
    ],
)
def test_strict_parameters_and_authority_are_not_model_supplied(args: dict) -> None:
    with pytest.raises(ValidationError):
        DateCalc.model_validate(args)


def test_prompt_r4_and_official_tool_description_are_present() -> None:
    text = load_prompts().render("system")
    assert "紧跟相对说法后加括号" in text and "下周三（10/28 周三）" in text
    assert "算了一下日期" in text and "有歧义时先确认" in text
    definition = next(
        item for item in computation_definitions() if item.name == "date_calc"
    )
    assert definition.description.startswith(
        "当你需要算天数、间隔、年龄、星期或农历公历互换时使用，不要心算。"
    )

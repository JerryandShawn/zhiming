"""Strict computation intents and deterministic dates do not need network or PG."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from mingjing_core.agent.tools.computation_definitions import computation_definitions
from mingjing_core.agent.tools.computation_parameters import ChartCompute, DateCalc, MemoryUpdate, ProfileUpdateRequest
from mingjing_core.application.agent_tools_computation import date_calc
from mingjing_core.domain.time_ranges import TimeRangeResult, UnavailableTimeRangeParser
from mingjing_core.models.schema_flatten import flatten_schema


@pytest.mark.parametrize(
    "date,days,expected",
    [
        ("2026-10-17", 4, "2026-10-21"),
        ("2024-02-28", 1, "2024-02-29"),
        ("2025-02-28", 1, "2025-03-01"),
        ("2026-12-31", 1, "2027-01-01"),
        ("2026-01-01", -1, "2025-12-31"),
    ],
)
def test_absolute_date_arithmetic(date: str, days: int, expected: str) -> None:
    result = date_calc({"operation": "add_days", "start_date": date, "days": days})
    assert result.ok and result.data["end_date"] == expected and result.data["days"] == days


def test_date_difference_has_no_inclusive_extra_day() -> None:
    result = date_calc({"operation": "difference", "start_date": "2026-10-17", "end_date": "2026-10-21"})
    assert result.data == {
        "start_date": "2026-10-17",
        "end_date": "2026-10-21",
        "start_weekday": 6,
        "end_weekday": 3,
        "days": 4,
        "difference_basis": "end_minus_start",
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"start_date": "下周三"},
        {"days": True},
        {"days": 1.2},
        {"start_date": "2026-02-30"},
        {"start_date": "20261017"},
        {"days": None},
        {"end_date": "2026-10-18"},
        {"timezone": "Asia/Tokyo"},
    ],
)
def test_absolute_arithmetic_rejects_guessing_and_extra_fields(changes: dict) -> None:
    with pytest.raises(ValidationError):
        DateCalc.model_validate({"operation": "add_days", "start_date": "2026-10-17", "days": 1, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"target": "今天"},
        {"birth": {"solar_datetime": "1994-01-01 00:00"}},
        {"owner": "other"},
        {"system": "tarot"},
        {"scale": "return"},
    ],
)
def test_chart_parameters_never_accept_runtime_identity_or_birth(changes: dict) -> None:
    with pytest.raises(ValidationError):
        ChartCompute.model_validate({"system": "bazi", "target": "2026-10-17", **changes})


def test_profile_request_contains_field_names_only_and_update_requires_revision() -> None:
    args = {"fields": ["birth.solar_datetime"], "message_id": "m", "quote": "请核对资料"}
    assert ProfileUpdateRequest.model_validate(args).fields == ["birth.solar_datetime"]
    for values in (
        {**args, "fields": {"birth.solar_datetime": "1994-01-01 00:00"}},
        {**args, "fields": ["password"]},
        {**args, "confirmed": True},
    ):
        with pytest.raises(ValidationError):
            ProfileUpdateRequest.model_validate(values)
    update = {"fact_id": "f", "message_id": "m", "quote": "更正", "summary": "摘要"}
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate(update)
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate(dict(update, expected_revision=True))


def test_registered_computation_definitions_flatten_without_mutating_default_registry() -> None:
    from mingjing_core.agent.toolkit import DEFINITIONS

    before = tuple(item.name for item in DEFINITIONS)
    definitions = computation_definitions()
    assert [item.name for item in definitions] == [
        "chart_compute",
        "date_calc",
        "memory_update",
        "profile_update_request",
        "chart_skill",
    ]
    for item in definitions:
        assert flatten_schema(item.parameters.model_json_schema())["type"] == "object"
        assert item.description
    # Reading definitions must not mutate the actual mainline registration.
    assert tuple(item.name for item in DEFINITIONS) == before


def test_unavailable_u4_is_an_explicit_clarification_substitute() -> None:
    parser = UnavailableTimeRangeParser()
    result = parser.parse_time_range("下周三面试", datetime.fromisoformat("2026-10-17T10:30:00+08:00"))
    assert result.needs_clarification and result.start is None and result.end is None and result.confidence == 0
    with pytest.raises(ValueError):
        parser.parse_time_range("下周三", datetime(2026, 10, 17))
    with pytest.raises(ValidationError):
        TimeRangeResult(start=datetime(2026, 10, 17))

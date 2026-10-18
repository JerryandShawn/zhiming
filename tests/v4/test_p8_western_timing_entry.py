"""Scoped subprocess entry: actual UTC techniques and read-only source evidence."""

from __future__ import annotations

import copy
import os
from typing import Any

import pytest

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.western_timing import validate_timing_request


def request(technique: str = "secondary_progressions") -> dict[str, Any]:
    args = {"birth_at": "2000-01-01T12:00:00Z", "target_at": "2025-01-01T12:00:00Z"}
    if technique == "solar_return":
        args = {
            "birth_at": "2000-01-01T12:00:00Z",
            "return_year": 2025,
            "longitude": 116.4,
            "latitude": 39.9,
        }
    return {
        "owner_user_id": "synthetic-western-owner",
        "subject_id": "synthetic-western-subject",
        "revision": 1,
        "operation_id": "synthetic-timing-1",
        "technique": technique,
        "args": args,
    }


@pytest.mark.parametrize("technique", ["secondary_progressions", "solar_return"])
def test_public_entry_uses_actual_charts_and_preserves_the_supplied_instant(
    technique: str,
) -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    adapter = P8ChartAdapter("synthetic-western-owner", python=python)
    value = request(technique)
    before = copy.deepcopy(value)
    result = adapter.western_timing(value)
    assert value == before
    assert result["model_calls"] == result["writes"] == 0
    assert result["time_basis"] == "actual_UTC_not_true_solar"
    assert not result["profile_update_allowed"]
    assert result["data"]["actual_UTC"]["birth_at"].startswith("2000-01-01T12:00:00")
    assert result["source_sha256"]["mingjing_core/adapters/charts/astro_ephemeris.py"]
    assert result["data"]["metadata"]
    from mingjing_core.skills import SkillLibrary

    topic = "returns" if technique == "solar_return" else "transits-progressions"
    chapter = next(
        row for row in SkillLibrary().chapters("astro") if row["topic"] == topic
    )
    capability = next(
        row for row in chapter["conditional_fields"] if row["capability"] == technique
    )
    for path in capability["paths"]:
        current = result
        for token in path.lstrip("/").split("/"):
            current = (
                current[int(token)] if isinstance(current, list) else current[token]
            )
        assert current is not None
    if technique == "solar_return":
        assert len(result["data"]["houses"]["cusps"]) == 12
        assert result["data"]["root"]["residual_degrees"] < 1e-6
        assert result["data"]["root"]["crossed_anniversary_year_boundary"]
    else:
        assert result["data"]["houses"] is None
        assert (
            result["data"]["mapping"]["progressed_jd_ut1"]
            > result["data"]["mapping"]["birth_jd_ut1"]
        )


def test_owner_is_rejected_before_any_worker_and_raw_longitudes_are_not_a_technique() -> (
    None
):
    adapter = P8ChartAdapter("another-owner", python="must-not-run")
    with pytest.raises(ValueError, match="归属"):
        adapter.western_timing(request())
    value = request()
    value["technique"] = "transit_windows"
    with pytest.raises(ValueError, match="登记"):
        validate_timing_request(value)


@pytest.mark.parametrize(
    "change",
    [
        {"revision": True},
        {"revision": -1},
        {"operation_id": ""},
        {"model": "forbidden"},
        {"args": {"birth_at": "2000-01-01T12:00:00Z"}},
    ],
)
def test_unscoped_or_unknown_parameters_cannot_enter_timing_worker(
    change: dict[str, Any],
) -> None:
    value = request()
    value.update(change)
    with pytest.raises(ValueError):
        validate_timing_request(value)

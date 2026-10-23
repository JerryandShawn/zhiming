"""Read-only Charts subprocess checks with explicit synthetic birth inputs."""

from __future__ import annotations

import copy
import importlib.util
import os
from importlib.resources import files

import pytest

from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter


def request() -> dict:
    return {
        "owner_user_id": "synthetic-time-owner",
        "subject_id": "synthetic-time-subject",
        "revision": 1,
        "operation_id": "synthetic-time-operation",
        "as_of_date": "2026-10-18",
        "birth": {
            "date": "1995-03-10",
            "reported_time": "09:40",
            "gender": "男",
            "place": {"tz": "Asia/Shanghai", "lon": 87.62, "lat": 43.83},
            "clock_basis": "clock",
            "precision": "reported",
        },
    }


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> P8ChartAdapter:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    # Test-only data source; deployment must install/lock tzdata in Charts itself.
    if importlib.util.find_spec("tzdata"):
        monkeypatch.setenv("PYTHONTZPATH", str(files("tzdata.zoneinfo")))
    return P8ChartAdapter("synthetic-time-owner", python=python)


def test_owner_is_rejected_before_any_child_process() -> None:
    adapter = P8ChartAdapter("other-owner", python="must-not-run")
    with pytest.raises(ValueError, match="归属"):
        adapter.time_basis(request())
    assert not hasattr(adapter, "rectify")


def test_exact_record_exposes_both_school_charts_without_double_conversion(adapter: P8ChartAdapter) -> None:
    from mingjing_core.adapters.charts.named_bazi import hidden_for, options

    value = request()
    before = copy.deepcopy(value)
    result = adapter.time_basis(value)
    assert value == before
    assert result["model_calls"] == result["writes"] == 0
    assert not result["profile_update_allowed"] and not result["life_event_scoring_performed"]
    assert result["time_basis"]["selected_basis"] == "true_solar"
    assert "top_three" not in result
    charts = {row["time_basis"]["basis"]: row for row in result["charts"]}
    assert set(charts) == {"standard", "true_solar", "beijing_standard"}
    assert charts["standard"]["data"]["pillars"]["hour"]["zhi"] == "巳"
    assert charts["true_solar"]["data"]["pillars"]["hour"]["zhi"] == "辰"
    for row in charts.values():
        expected = row["time_basis"]["coordinate_datetime"].replace("T", " ")[:16]
        assert row["ziwei_column"]["corrected_time"] == expected
        assert row["ziwei_column"]["time_basis"] == row["time_basis"]["basis"]
        assert row["data"]["p8"]["month_command"]["exact_seconds_preserved"]
        command = row["data"]["p8"]["month_command"]
        assert command["period_start"] < command["calendar_birth_at"] < command["period_end_exclusive"]
        for decade in row["data"]["p8"]["decade_luck"]["decades"]:
            assert [item["stem"] for item in decade["hidden_ten_gods"]] == list(
                hidden_for(options())[decade["ganzhi"][1]]
            )


def test_nonexistent_clock_is_not_silently_shifted_or_scored(adapter: P8ChartAdapter) -> None:
    value = request()
    value["birth"].update(date="1988-04-17", reported_time="02:30")
    result = adapter.time_basis(value)
    assert result["charts"] == []
    assert result["time_basis"]["instants"][0]["status"] == "nonexistent"
    assert result["time_basis"]["requires_confirmation"]


def test_precise_seconds_survive_physical_start_and_school_comparison(adapter: P8ChartAdapter) -> None:
    value = request()
    value["birth"]["reported_time"] = "23:00:37"
    result = adapter.time_basis(value)
    for row in result["charts"]:
        assert row["time_basis"]["calendar_datetime"].endswith(":37")
        assert row["data"]["p8"]["month_command"]["calendar_birth_at"].endswith(":37+08:00")


def test_unknown_time_is_not_routed_into_life_event_ranking(adapter: P8ChartAdapter) -> None:
    value = request()
    value["birth"]["precision"] = "unknown"
    with pytest.raises(RuntimeError, match="chart_engine_failure"):
        adapter.time_basis(value)


@pytest.mark.parametrize(
    "change",
    [
        {"revision": -1},
        {"revision": True},
        {"as_of_date": "1990-01-01"},
        {"as_of_date": "20261018"},
        {"as_of_date": "2026-W42-7"},
    ],
)
def test_invalid_scope_or_future_birth_cannot_produce_a_chart(change: dict) -> None:
    from mingjing_core.adapters.charts.time_basis_request import validate_request

    value = request()
    value.update(change)
    with pytest.raises(ValueError):
        validate_request(value)


def test_initial_revision_zero_and_birth_scope_are_checked_without_heavy_engines() -> None:
    from mingjing_core.adapters.charts.time_basis_request import validate_request

    value = request()
    value["revision"] = 0
    validate_request(value)
    value["birth"]["subject_id"] = "a-different-subject"
    with pytest.raises(ValueError, match="归属或人物"):
        validate_request(value)


def test_review23_default_and_beijing_comparison_for_an_overseas_record(adapter: P8ChartAdapter) -> None:
    from datetime import UTC, datetime, timedelta

    value = request()
    value["birth"].update(
        date="2010-01-15", reported_time="12:00", place={"tz": "America/New_York", "lon": -74, "lat": 40.7}
    )
    result = adapter.time_basis(value)
    charts = {row["time_basis"]["basis"]: row for row in result["charts"]}
    assert charts["standard"]["time_basis"]["coordinate_datetime"].startswith("2010-01-15T12:00")
    bj = charts["beijing_standard"]["time_basis"]
    actual = datetime.fromisoformat(bj["utc"].replace("Z", "+00:00")).astimezone(UTC)
    assert datetime.fromisoformat(bj["coordinate_datetime"]) == (actual + timedelta(hours=8)).replace(tzinfo=None)
    assert result["interpretation"]["primary_chart_ids"] == [charts["true_solar"]["id"]]
    assert result["interpretation"]["comparisons"][0]["text"].startswith("按北京时间则为")
    assert charts["true_solar"]["visible_by_default"] and charts["beijing_standard"]["visible_by_default"]
    assert not charts["standard"]["visible_by_default"]
    assert result["profile_basis_record"]["basis"] == "true_solar"
    assert result["profile_basis_record"]["writes"] == 0
    assert result["release_policy"]["rectification"]["status"] == "experimental_frozen"
    assert result["time_basis"]["requires_confirmation"] is False


def test_every_nested_flying_evidence_pointer_resolves_in_the_complete_response(adapter: P8ChartAdapter) -> None:
    result = adapter.time_basis(request())
    pointers = []

    def collect(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key.endswith("_pointer"):
                    pointers.append(item)
                elif key == "evidence_paths":
                    pointers.extend(item)
                else:
                    collect(item)

    for chart in result["charts"]:
        flying = chart["ziwei_column"]["p8_flying_transformations"]
        assert flying["evidence_document_root"] == "complete_time_basis_response"
        collect(flying)
    assert len(pointers) > 100
    for pointer in pointers:
        assert pointer.startswith("/charts/")
        actual = result
        for token in pointer.lstrip("/").split("/"):
            actual = actual[int(token)] if isinstance(actual, list) else actual[token]
        assert actual is not None

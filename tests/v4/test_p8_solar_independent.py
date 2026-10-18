"""Fixed-grid EOT research checks; numerical gates never alter the production method."""

from __future__ import annotations

import json
import math
import os
import subprocess
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.night24_solar_reference import (
    THRESHOLD_SECONDS,
    digest,
    grid,
    summarize,
)

ROOT = Path(__file__).resolve().parents[2]


def test_fixed_grid_covers_every_declared_year_and_all_leap_days() -> None:
    moments = grid()
    assert len(moments) == len(set(moments)) == 8156
    assert {moment.year for moment in moments} == set(range(1901, 2100))
    assert moments[0].isoformat() == "1901-01-01T00:00:00+00:00"
    assert moments[-1].isoformat() == "2099-12-31T23:59:59+00:00"
    assert sum(moment.month == 2 and moment.day == 29 for moment in moments) == 49 * 4
    assert len(digest([moment.isoformat() for moment in moments])) == 64


def test_statistics_report_fixed_nearest_rank_tail_and_signed_mean() -> None:
    result = summarize(list(range(1, 21)))
    assert result["count"] == 20
    assert result["max_abs_seconds"] == 20
    assert result["p95_abs_seconds_nearest_rank"] == 19
    assert result["mean_signed_seconds"] == 10.5
    assert result["rms_seconds"] == math.sqrt(143.5)
    assert result["over_fixed_5_second_alarm"] == 15


def test_research_alarm_is_fixed_and_keeps_exceedances() -> None:
    assert THRESHOLD_SECONDS == 5
    assert summarize([-5, 5])["sampled_research_alarm_clear"] is True
    assert summarize([-5.001, 0])["sampled_research_alarm_clear"] is False
    assert summarize([-5.001, 0])["over_fixed_5_second_alarm"] == 1


@pytest.mark.parametrize(
    "values", [[], [float("nan")], [float("inf")], [float("-inf")]]
)
def test_empty_or_nonfinite_study_statistics_are_rejected(values: list[float]) -> None:
    with pytest.raises(ValueError):
        summarize(values)


def test_real_swiss_grid_and_honest_boundary_disagreements(tmp_path: Path) -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    destination = tmp_path / "solar-independent.json"
    environment = {
        key: value for key, value in os.environ.items() if not key.endswith("API_KEY")
    }
    environment.update(
        PYTHONUTF8="1", LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false"
    )
    process = subprocess.run(
        [
            python,
            "-X",
            "utf8",
            "-m",
            "mingjing_core.adapters.charts.benchmarks.night24_solar_independent",
            "--output",
            str(destination),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    result = json.loads(destination.read_text(encoding="utf-8"))
    assert result["grid"]["sample_count"] == 8156
    assert result["fixed_alarm_seconds"] == 5
    assert result["status"] == "offline_research_not_product_acceptance"
    assert result["production_method_changed"] is False
    assert (
        result["live_model_calls"]
        == result["network_calls"]
        == result["database_writes"]
        == 0
    )
    assert result["reference"]["companion_calc_ut_flags"] == [2052]
    assert "companion-call" in result["reference"]["flags_limit"]
    assert result["statistics"]["noaa_minus_swiss_eot_seconds"][
        "sampled_research_alarm_clear"
    ]
    boundary = result["boundary_study"]
    assert boundary["probe_count"] == len(boundary["rows"]) == 42
    assert boundary["day_hour_disagreements"] == sum(
        not row["same_day_hour"] for row in boundary["rows"]
    )
    assert boundary["day_pillar_disagreements"] == 2
    assert boundary["hour_pillar_disagreements"] == 5
    assert boundary["thirty_second_control_disagreements"] == 0

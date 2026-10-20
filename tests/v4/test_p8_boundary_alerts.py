"""Threshold contracts and one isolated native boundary-regression process."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta
from importlib.resources import files
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.boundary_alerts import _near_clock, boundary_alerts

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("seconds", [-901, -900, -899, 0, 899, 900, 901])
@pytest.mark.parametrize("hour", [0, 1, 7, 23])
def test_clock_alert_threshold_is_inclusive_with_exact_seconds(
    seconds: int, hour: int
) -> None:
    boundary = datetime(2026, 10, 21, hour)
    matches = _near_clock(boundary + timedelta(seconds=seconds), (hour,), 900)
    assert bool(matches) is (abs(seconds) <= 900)
    if matches:
        assert matches == [(boundary, abs(seconds))]


def test_empty_candidates_do_not_import_or_guess_a_native_engine() -> None:
    assert boundary_alerts({"items": []}) == []


def test_native_real_boundary_alerts_are_not_fixture_only() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = {
        key: value for key, value in os.environ.items() if "API_KEY" not in key.upper()
    }
    env.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONUTF8="1")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_boundary_alerts_native.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"tests": 12, "successful": True, "skipped": 0}

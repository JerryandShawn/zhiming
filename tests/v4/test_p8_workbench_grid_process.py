"""Run only the short synthetic chart-grid checks in the real Charts runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_real_short_grid_and_frozen_annual_cache_in_charts() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = dict(os.environ)
    for key in env:
        if key.endswith("_API_KEY"):
            env[key] = ""
    env.update(
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        PYTHONIOENCODING="utf-8",
    )
    if importlib.util.find_spec("tzdata"):
        env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_workbench_grid_native.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {
        "tests": 10,
        "successful": True,
        "skipped": 0,
    }

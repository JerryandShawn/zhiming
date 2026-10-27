"""Run all four R46 probes in one isolated Charts process, with no engine mocks."""

from __future__ import annotations

import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest


def test_r46_before_after_119_minutes_warn_and_121_minutes_do_not() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    root = Path(__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if "API_KEY" not in k.upper()}
    env.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONUTF8="1")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    result = subprocess.run(
        [python, "-X", "utf8", str(root / "tests/test_p8_jie_window_r46_native.py")],
        cwd=root,
        env=env,
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "cases": [
            {"offset_seconds": -7260, "alert": False},
            {"offset_seconds": -7140, "alert": True},
            {"offset_seconds": 7140, "alert": True},
            {"offset_seconds": 7260, "alert": False},
        ],
        "real_model_calls": 0,
    }

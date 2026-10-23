"""Run native P8 checks in the explicitly configured isolated Charts process."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_configured_chart_interpreter_runs_native_p8_suite() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured isolated CHART_PYTHON")
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tools/verify_p8_calculators.py")],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, "isolated P8 checks failed (private stderr deliberately omitted)"
    result = json.loads(process.stdout)
    assert result["native_tests"] == {"tests": 16, "failures": 0, "errors": 0, "skipped": 0, "successful": True}
    assert result["independent_status"] == "not_run"

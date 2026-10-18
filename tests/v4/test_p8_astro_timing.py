"""Core bridge: real Swiss calculations stay in the explicitly selected Charts process."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_native_western_timing_with_independent_cached_ephemeris() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_astro_native.py")],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=180,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"tests": 21, "successful": True, "skipped": 0}

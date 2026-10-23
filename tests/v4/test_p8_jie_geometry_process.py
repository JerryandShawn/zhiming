"""Run retained Jie geometry invariants with the actual isolated lunar engine."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


def test_strict_jie_sides_and_range_clipping_with_real_engine() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    root = Path(__file__).resolve().parents[2]
    process = subprocess.run(
        [
            python,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_p8_jie_geometry_native.py",
        ],
        cwd=root,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
    assert "Ran 3 tests" in process.stderr and "OK" in process.stderr

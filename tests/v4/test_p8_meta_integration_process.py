"""Core-to-Charts bridge for real P8 integration and profile proposal checks."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_native_meta_integration_wiring() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured isolated CHART_PYTHON")
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_meta_integration.py")],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=180,
    )
    assert process.returncode == 0, (
        "P8 meta integration failed; inspect native synthetic test output locally"
    )
    result = json.loads(process.stdout)
    assert result == {
        "tests": 14,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "successful": True,
    }

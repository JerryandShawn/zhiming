"""Exercise independent relation-member checks in the configured Charts process."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_native_daily_and_window_members_remain_consistent() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured isolated CHART_PYTHON")
    process = subprocess.run(
        [
            python,
            "-X",
            "utf8",
            str(ROOT / "tests/test_p8_daily_window_members_native.py"),
        ],
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        timeout=60,
    )
    assert process.returncode == 0, (
        "independent native relation-member checks failed; private output omitted"
    )
    assert json.loads(process.stdout) == {
        "tests": 3,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "successful": True,
    }

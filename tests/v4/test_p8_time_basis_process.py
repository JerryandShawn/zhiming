"""Share explicit tzdata bytes with Charts, without changing either runtime."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest

from mingjing_core.adapters.charts import time_basis_zones
from mingjing_core.adapters.charts.time_basis import resolve_birth_instants

ROOT = Path(__file__).resolve().parents[2]


def _environment() -> dict[str, str]:
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
    return env


def test_native_time_basis_with_explicit_tzdata() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_time_basis_native.py")],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        encoding="utf-8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    summary = json.loads(process.stdout)
    assert summary == {"tests": 8, "successful": True, "skipped": 0}


def test_core_and_charts_same_tzfile_have_same_physical_fold_instants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    # Reproduce Linux with a stale system database and a newer locked package.
    if importlib.util.find_spec("tzdata"):
        target = tmp_path / "Asia" / "Shanghai"
        target.parent.mkdir()
        target.write_bytes(
            files("tzdata.zoneinfo").joinpath("Asia", "Shanghai").read_bytes()
        )
        (tmp_path / "tzdata.zi").write_text(
            "# version unpinned-system-test\n", encoding="utf-8"
        )
        monkeypatch.setattr(time_basis_zones.zoneinfo, "TZPATH", (str(tmp_path),))
        monkeypatch.delenv("PYTHONTZPATH", raising=False)
    code = (
        "import json; from mingjing_core.adapters.charts.time_basis import resolve_birth_instants;"
        "print(json.dumps(resolve_birth_instants('1988-09-11','01:30',{'tz':'Asia/Shanghai'},'clock')))"
    )
    process = subprocess.run(
        [python, "-c", code],
        cwd=ROOT,
        env=_environment(),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    actual = json.loads(process.stdout)
    expected = resolve_birth_instants(
        "1988-09-11", "01:30", {"tz": "Asia/Shanghai"}, "clock"
    )
    assert [(row["id"], row["utc"], row["standard"]) for row in actual] == [
        (row["id"], row["utc"], row["standard"]) for row in expected
    ]

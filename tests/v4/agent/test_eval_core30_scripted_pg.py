"""All core30 scripts run through actual local PG and the locked calculator worker."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tools.eval import runner
from tools.eval.targets.v4_core30 import CORE30_IDS

from .test_eval_v4_pg import target as target_fixture


def test_core30_scripted_cli_uses_real_tools_without_external_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    native_run = subprocess.run
    fixture = target_fixture.__wrapped__(monkeypatch)
    target = next(fixture)
    root = Path(__file__).resolve().parents[3]
    chart_python = os.environ.get("CHART_PYTHON", "")
    assert chart_python and Path(chart_python).is_file()
    worker = [chart_python, "-X", "utf8", str(root / "mingjing_core/adapters/charts/worker.py")]

    def calculator_only(command, *args, **kwargs):
        if command != worker or kwargs.get("shell"):
            raise AssertionError("Only the locked local calculator worker may launch")
        return native_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", calculator_only)
    monkeypatch.setattr(runner, "_target", lambda *_: target)
    output = tmp_path / "core30-scripted"
    try:
        code = runner.main(["--mode", "scripted", "--target", "v4", "--suite", "core30", "--output", str(output)])
        report = json.loads(next(output.glob("*.json")).read_text(encoding="utf-8"))
        assert code == 0, [(row["id"], row["failed_assertions"]) for row in report["cases"] if row["status"] != "passed"]
        assert tuple(row["id"] for row in report["cases"]) == CORE30_IDS
        assert report["summary"]["count"] == report["summary"]["passed"] == 30
        assert report["metadata"]["status"] == "complete"
        assert report["metadata"]["external_provider_requests"] == 0
        assert all(row["v4_evidence"]["external_provider_requests"] == 0 for row in report["cases"])
    finally:
        target.close()
        try:
            next(fixture)
        except StopIteration:
            pass

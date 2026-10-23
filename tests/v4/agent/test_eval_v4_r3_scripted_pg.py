"""Exercise the complete P3 scripted CLI after the authorized R3 contract split."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tools.eval import runner
from tools.eval.targets.v4_corpus import REQUIRED_IDS
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def test_p3_scripted_cli_passes_all_48_cases_after_r3(
    target: V4Target,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    record_property: Callable[[str, object], None],
) -> None:
    output = tmp_path / "p3-r3-scripted"
    monkeypatch.setattr(runner, "_target", lambda *_: target)
    result = runner.main(["--target", "v4", "--mode", "scripted", "--output", str(output)])
    assert result == 0
    report_path = next(output.glob("*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert {case["id"] for case in report["cases"]} == REQUIRED_IDS
    assert report["summary"]["count"] == report["summary"]["passed"] == 48
    assert report["metadata"]["status"] == "complete"
    assert report["metadata"]["external_provider_requests"] == 0
    assert all(case["v4_evidence"]["external_provider_requests"] == 0 for case in report["cases"])
    record_property("p3_scripted_cases", "48/48")
    record_property("scripted_report", str(report_path))

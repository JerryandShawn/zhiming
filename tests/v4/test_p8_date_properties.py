"""Research harness rejects invalid plans and notices broken evidence bindings."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date, timedelta
from importlib.resources import files
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.night28_date_cases import (
    corpus,
    dst_anchors,
    target_days,
)
from mingjing_core.adapters.charts.benchmarks.night28_property_common import (
    alias_checks,
)
from mingjing_core.adapters.charts.tool_evidence import evidence_result

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("count", [True, 0, 1, 3, 1001, 1004, -4, "1000"])
def test_invalid_sampling_plan_fails_before_importing_calendar(count: object) -> None:
    with pytest.raises(ValueError, match="count_must_be_divisible_by_four"):
        corpus(None, count)


def test_annual_manifest_is_every_day_not_sparse_sampling() -> None:
    days = target_days()
    assert len(days) == len(set(days)) == 730
    assert days[0] == "2026-01-01" and days[-1] == "2027-12-31"
    for left, right in zip(days[:-1], days[1:], strict=True):
        assert date.fromisoformat(right) - date.fromisoformat(left) == timedelta(days=1)
    anchors = dst_anchors()
    assert len(anchors) == 12
    assert sum(row["expected"] == "nonexistent" for row in anchors) == 6
    assert sum(row["expected"] == "ambiguous" for row in anchors) == 6


def test_research_alias_check_rejects_corrupt_values_and_source_claims() -> None:
    hit = {
        "rule_id": "synthetic-test",
        "met": True,
        "school": "synthetic-test",
        "source": "synthetic-test",
        "evidence_paths": ["/data/value"],
    }
    result = evidence_result(
        "synthetic-test-only", {"value": 1}, [hit], ["synthetic-test"]
    )
    assert alias_checks(result)
    result["aliases"]["r"][0]["evidence_aliases"] = ["c999"]
    assert not alias_checks(result)
    result["aliases"]["r"][0]["evidence_aliases"] = ["c1"]
    result["data"]["value"] = 2
    assert not alias_checks(result)


def test_small_native_property_rehearsal_uses_actual_calendar(tmp_path: Path) -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = {
        key: value for key, value in os.environ.items() if "API_KEY" not in key.upper()
    }
    env.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONUTF8="1")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    output = tmp_path / "small-property-report.json"
    process = subprocess.run(
        [
            python,
            "-m",
            "mingjing_core.adapters.charts.benchmarks.night28_date_properties",
            "--mode",
            "scripted",
            "--suite",
            "random",
            "--count",
            "20",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=90,
    )
    assert process.returncode == 0, process.stderr
    report = json.loads(output.read_text(encoding="utf8"))
    random = report["calendar"]["random_unique_dates"]
    assert random["cases"] == random["unique_reported_dates"] == 20
    assert random["categories"] == {"dst": 5, "leap_month": 5, "jie": 5, "late_zi": 5}
    assert random["failure_count"] == 0
    assert report["calendar"]["additional_DST_anchors"]["failure_count"] == 0
    assert report["model_calls"] == report["writes_to_profiles"] == 0

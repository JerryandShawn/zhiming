"""One subprocess for actual offline window-search integration and a sample schema."""

from __future__ import annotations

import json
import os
import subprocess
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def test_window_schema_is_valid_draft_2020_12() -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts/window_search.schema.json").read_text(
            encoding="utf8"
        )
    )
    Draft202012Validator.check_schema(schema)


def test_real_synthetic_sample_matches_schema_and_recomputes_scores() -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts/window_search.schema.json").read_text(
            encoding="utf8"
        )
    )
    path = (
        ROOT / "docs/v4/contracts/samples/window-search-ayuan-contract-20261021-27.json"
    )
    sample = json.loads(path.read_text(encoding="utf8"))
    Draft202012Validator(schema).validate(sample)
    assert len(sample["data"]["candidates"]) == 7
    for candidate in sample["data"]["candidates"]:
        links = (
            candidate["positive_hits"]
            + candidate["negative_hits"]
            + candidate["neutral_hits"]
        )
        assert candidate["score"] == sum(
            sample["rule_hits"][row["rule_hit_index"]]["contribution"] for row in links
        )


def test_native_window_default_path_computes_real_daily_charts() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = {
        key: value for key, value in os.environ.items() if "API_KEY" not in key.upper()
    }
    env.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false", PYTHONUTF8="1")
    env["PYTHONTZPATH"] = str(files("tzdata.zoneinfo"))
    process = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_window_search_native.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout) == {"tests": 6, "successful": True, "skipped": 0}

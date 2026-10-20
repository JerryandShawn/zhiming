"""Core-only contract checks plus one explicit isolated native-engine bridge."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.adapters.charts.daily_transit import daily_transit, prepare_natal
from mingjing_core.adapters.charts.daily_transit_natal import snapshot
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "docs/v4/contracts/samples/daily_transit"


@pytest.mark.parametrize(
    "value",
    [
        "20261021",
        "２０２６-１０-２１",
        "2026-2-1",
        "2026-W43-3",
        "2026-10-21T00:00:00Z",
        "2026-10-21Z",
        "2026-02-30",
        "2026-13-01",
        "",
        None,
        True,
    ],
)
def test_snapshot_rejects_non_iso_or_invalid_dates(value: Any) -> None:
    with pytest.raises(ValueError, match="daily_transit_date_invalid"):
        snapshot(value)


@pytest.mark.parametrize("value", ["1900-12-31", "2100-01-01"])
def test_explicit_supported_range_is_enforced(value: str) -> None:
    with pytest.raises(ValueError, match="daily_transit_date_out_of_range"):
        snapshot(value)


def test_snapshot_before_birth_refuses_without_using_system_today() -> None:
    with pytest.raises(ValueError, match="daily_transit_before_birth"):
        snapshot("1990-01-01", "1994-03-12")
    assert snapshot("2026-10-21").isoformat() == "2026-10-21T12:00:00+08:00"


@pytest.mark.parametrize("value", [None, [], "private-invalid-natal", 1, True])
def test_nonobject_natal_is_rejected_before_loading_native_dependencies(
    value: Any,
) -> None:
    with pytest.raises(ValueError, match="daily_transit_natal_object_required"):
        prepare_natal(value, "2026-10-21")


@pytest.mark.parametrize(
    "value", [True, None, "2", -0.1, 10.1, float("nan"), float("inf")]
)
def test_invalid_orb_is_rejected_before_any_birth_calculation(value: Any) -> None:
    with pytest.raises(ValueError, match="西占计算参数"):
        daily_transit({}, "2026-10-21", orb_degrees=value)


@pytest.mark.parametrize("day", range(21, 28))
def test_seven_actual_engine_samples_validate_schema_and_evidence(day: int) -> None:
    schema = json.loads(
        (ROOT / "docs/v4/contracts/daily_transit.schema.json").read_text("utf8")
    )
    Draft202012Validator.check_schema(schema)
    result = json.loads((SAMPLES / f"ayuan_2026-10-{day}.json").read_text("utf8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)
    content = {
        key: result[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    assert result["document_id"] == "tool-" + content_hash(content)
    paths = sorted(
        {path for row in result["rule_hits"] for path in row["evidence_paths"]}
    )
    assert [row["path"] for row in result["aliases"]["c"]] == paths
    for alias in result["aliases"]["c"] + result["aliases"]["r"]:
        assert alias["value_sha256"] == content_hash(pointer(result, alias["path"]))
    assert {hit["context"]["system"] for hit in result["rule_hits"]} == {
        "bazi",
        "ziwei",
        "astro",
    }
    assert result["scope"]["subject_id"] == "synthetic-subject-ayuan"
    assert result["effects"]["writes"] == result["effects"]["model_calls"] == 0


def test_sample_manifest_dates_and_hashes_match_actual_documents() -> None:
    manifest = json.loads((SAMPLES / "manifest.json").read_text("utf8"))
    assert len(manifest["files"]) == 7
    for day, item in zip(range(21, 28), manifest["files"], strict=True):
        result = json.loads((SAMPLES / item["file"]).read_text("utf8"))
        assert item["date"] == result["data"]["date"] == f"2026-10-{day}"
        assert item["document_id"] == result["document_id"]
        assert item["hits"] == len(result["rule_hits"])
        assert item["r"] == len(result["aliases"]["r"])


def test_native_daily_calendar_ziwei_swiss_and_boundary_invariants() -> None:
    python = os.environ.get("CHART_PYTHON")
    if not python:
        pytest.skip("requires explicitly configured CHART_PYTHON")
    env = {
        key: value
        for key, value in os.environ.items()
        if "API_KEY" not in key.upper()
        and not key.upper().startswith(("LANGCHAIN", "LANGSMITH"))
    }
    env.update(PYTHONUTF8="1", LANGCHAIN_TRACING_V2="false", LANGSMITH_TRACING="false")
    result = subprocess.run(
        [python, "-X", "utf8", str(ROOT / "tests/test_p8_daily_transit_native.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        encoding="utf8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"tests": 14, "successful": True, "skipped": 0}

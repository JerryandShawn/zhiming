"""42/D5: prove the documented root mapping against actual-engine fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import pointer
from mingjing_core.adapters.charts.benchmarks.handoff_validate import validate_preview
from mingjing_core.skills.wiring_index import skill_index

SAMPLES = Path(__file__).resolve().parents[2] / "docs/v4/contracts/samples"


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_documented_pointer_lift_resolves_every_assessment(system: str) -> None:
    preview = json.loads((SAMPLES / f"ayuan_{system}.json").read_text(encoding="utf8"))
    payload = next(
        row["payload"] for row in preview["documents"] if "charts" in row["payload"]
    )
    count = 0
    for index, chart in enumerate(payload["charts"]):
        for row in chart["data"]["p8"]["rule_assessments"]:
            for path in row["evidence_paths"]:
                assert path.startswith("/data/")
                assert pointer(payload, f"/charts/{index}" + path) == pointer(
                    {"data": chart["data"]}, path
                )
                count += 1
    assert count > 0
    for alert in payload["boundary_alerts"]:
        assert all(
            pointer(payload, path) is not None for path in alert["evidence_paths"]
        )
    documents = {row["document_id"]: row["payload"] for row in preview["documents"]}
    for alias in preview["aliases"]["r"]:
        ref = alias["ref"]
        hit = pointer(documents[ref["document_id"]], ref["path"])
        assert hit["met"] is True


def test_mainline_cases_map_confirmed_fields_to_actual_sample_requests() -> None:
    material = json.loads((SAMPLES / "p8-wiring-cases.json").read_text(encoding="utf8"))
    assert material["synthetic"] is True and len(material["cases"]) == 3
    for case in material["cases"]:
        preview = json.loads(
            (SAMPLES / case["expected_preview_file"]).read_text(encoding="utf8")
        )
        validate_preview(preview, verify_runtime_sources=True)
        profile = case["confirmed_profile_fixture"]
        birth = preview["request"]["birth"]
        assert (
            profile["birth.solar_datetime"]
            == birth["date"] + "T" + birth["reported_time"] + ":00"
        )
        assert profile["birth.location"]["tz"] == birth["place"]["tz"]
        assert profile["birth.location"]["lng"] == birth["place"]["lon"]
        assert profile["birth.location"]["lat"] == birth["place"]["lat"]
        assert profile["birth.clock_basis"] == birth["clock_basis"]
        assert profile["birth.precision"] == birth["precision"] == "reported"
        assert case["input_scope"] == preview["scope"]
        assert case["documents"] == [
            {"document_id": row["document_id"], "kind": row["kind"]}
            for row in preview["documents"]
        ]
        assert case["not_agent_runtime_acceptance"] is True


def test_exported_skill_index_is_current_and_complete() -> None:
    exported = json.loads((SAMPLES / "p8-skill-index.json").read_text(encoding="utf8"))
    assert exported == skill_index()

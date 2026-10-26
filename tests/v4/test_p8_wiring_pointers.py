"""42/D5: prove the documented root mapping against actual-engine fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import pointer

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

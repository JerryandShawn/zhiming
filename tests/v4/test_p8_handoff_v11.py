"""Additive warnings preserve v1 reads while making v1.1 warnings accountable."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import resolve
from mingjing_core.adapters.charts.benchmarks.handoff_validate import validate_preview
from mingjing_core.adapters.charts.tool_evidence import evidence_result, pointer

SAMPLES = Path(__file__).resolve().parents[2] / "docs/v4/contracts/samples"


def preview(system: str) -> dict:
    return json.loads((SAMPLES / f"ayuan_{system}.json").read_text(encoding="utf8"))


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_v11_boundary_refs_real_alternatives_and_aliases(system: str) -> None:
    value = preview(system)
    validate_preview(value, verify_runtime_sources=True)
    assert value["contract_version"] == "p8-chart-compute-preview-v1.1"
    assert value["boundary_alerts"] == value["view"]["boundary_alerts"]
    assert len(value["boundary_alerts"]) == 1
    docs = {row["document_id"]: row["payload"] for row in value["documents"]}
    ref = value["boundary_alerts"][0]
    hit = resolve(docs[ref["document_id"]], ref["path"])
    assert hit["boundary_kind"] == "hour_branch"
    assert hit["met"] and hit["critical"] and not hit["default_formula_changed"]
    assert len({row["pillars"]["hour"] for row in hit["alternatives"]}) == 2
    rules = [row for row in value["aliases"]["r"] if row["ref"] == ref]
    assert len(rules) == 1 and rules[0]["basis"] == "true_solar"
    assert rules[0]["evidence_aliases"]


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_v1_envelope_without_v11_views_remains_readable(system: str) -> None:
    value = preview(system)
    value["contract_version"] = "p8-chart-compute-preview-v1"
    value.pop("boundary_alerts")
    value["view"].pop("boundary_alerts")
    value["aliases"]["r"] = [
        row
        for row in value["aliases"]["r"]
        if not row["ref"]["path"].startswith("/boundary_alerts/")
    ]
    validate_preview(value)


@pytest.mark.parametrize("mutation", ["omit", "drop_view", "drop_r", "foreign_ref"])
def test_v11_cannot_silently_drop_or_redirect_warnings(mutation: str) -> None:
    value = preview("bazi")
    if mutation == "omit":
        value.pop("boundary_alerts")
    elif mutation == "drop_view":
        value["view"]["boundary_alerts"] = []
        value["boundary_alerts"] = []
    elif mutation == "drop_r":
        value["aliases"]["r"] = value["aliases"]["r"][:-1]
    else:
        value["boundary_alerts"][0]["path"] = "/time_basis"
    with pytest.raises(ValueError):
        validate_preview(value)


def hit(path: str = "/data/value") -> dict:
    return {
        "rule_id": "test.value",
        "met": True,
        "school": "test convention",
        "source": "synthetic mathematical fixture",
        "evidence_paths": [path],
    }


def test_pure_tool_evidence_hashes_inputs_and_sources_without_mutation() -> None:
    data, hits, sources = {"value": 4}, [hit()], ["synthetic"]
    original = deepcopy([data, hits, sources])
    first = evidence_result("test-v1", data, hits, sources)
    assert [data, hits, sources] == original
    assert pointer(first, first["aliases"]["c"][0]["path"]) == 4
    assert first["aliases"]["r"][0]["evidence_aliases"] == ["c1"]
    assert first == evidence_result("test-v1", data, hits, sources)
    assert (
        first["document_id"]
        != evidence_result("test-v1", {"value": 5}, hits, sources)["document_id"]
    )
    assert (
        first["document_id"]
        != evidence_result("test-v1", data, hits, ["changed"])["document_id"]
    )
    first["data"]["value"] = 8
    assert data == {"value": 4}


@pytest.mark.parametrize("bad", [False, None, "true", 1])
def test_false_unknown_or_nonboolean_hits_cannot_receive_r(bad) -> None:
    row = hit()
    row["met"] = bad
    with pytest.raises(ValueError, match="true_sourced"):
        evidence_result("test-v1", {"value": 4}, [row], ["synthetic"])


@pytest.mark.parametrize(
    "path", ["/data/missing", "/data/a/01", "/data/a/-1", "/data/~2", "/rule_hits/0"]
)
def test_pure_tool_aliases_require_existing_strict_data_pointers(path: str) -> None:
    with pytest.raises(ValueError):
        evidence_result("test-v1", {"a": [1]}, [hit(path)], ["synthetic"])

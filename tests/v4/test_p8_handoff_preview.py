"""Document roots, honest aliases and native data in the synthetic handoff."""

from __future__ import annotations

import json
import os
import socket
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_build import BIRTH, TARGET
from mingjing_core.adapters.charts.benchmarks.handoff_offline import offline_runtime
from mingjing_core.adapters.charts.benchmarks.handoff_refs import (
    claim_id,
    digest,
    document_id,
    resolve,
)
from mingjing_core.adapters.charts.benchmarks.handoff_schema import schema
from mingjing_core.adapters.charts.benchmarks.handoff_validate import validate_preview
from mingjing_core.adapters.charts.benchmarks.handoff_validate_data import utc

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "docs/v4/contracts/samples"


@pytest.fixture(scope="module")
def originals() -> dict:
    return {
        system: json.loads(
            (SAMPLES / f"ayuan_{system}.json").read_text(encoding="utf8")
        )
        for system in ("bazi", "ziwei", "astro")
    }


def value(preview: dict, ref: dict):
    doc = next(
        row for row in preview["documents"] if row["document_id"] == ref["document_id"]
    )
    return resolve(doc["payload"], ref["path"])


def rebind(preview: dict, doc: dict) -> None:
    before = doc["document_id"]
    after = document_id(
        preview["scope"], doc["kind"], doc["source_sha256"], doc["payload"]
    )
    doc["document_id"] = after
    for group in preview["view"].values():
        for ref in group:
            if ref["document_id"] == before:
                ref["document_id"] = after
    for group in preview["aliases"].values():
        for row in group:
            if row["ref"]["document_id"] == before:
                row["ref"]["document_id"] = after
                row["value_sha256"] = digest(value(preview, row["ref"]))
            row["claim_id"] = claim_id(row)


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_three_real_calculation_fixtures_validate_without_mutation(
    originals: dict, system: str
) -> None:
    preview = deepcopy(originals[system])
    before = deepcopy(preview)
    validate_preview(preview, verify_runtime_sources=True)
    assert preview == before
    assert preview["request"]["birth"] == BIRTH
    assert preview["request"]["target_date"] == TARGET
    assert preview["request"]["physical_birth_at_utc"] == "1994-03-12T00:20:00Z"
    assert preview["effects"] == {
        "model_calls": 0,
        "writes": 0,
        "alias_registry": "ephemeral_demo_only",
    }


def test_schema_export_matches_builder_and_each_file_has_unique_operation(
    originals: dict,
) -> None:
    assert (
        json.loads(
            (SAMPLES.parent / "chart_compute.schema.json").read_text(encoding="utf8")
        )
        == schema()
    )
    assert len({row["scope"]["operation_id"] for row in originals.values()}) == 3


def test_same_pillars_do_not_create_a_visible_disagreement(originals: dict) -> None:
    for system in ("bazi", "ziwei"):
        preview = originals[system]
        raw = preview["documents"][0]["payload"]
        assert raw["interpretation"]["comparisons"] == []
        assert preview["view"]["comparisons"] == []
        assert len(preview["view"]["primary"]) == 1
        assert len(preview["view"]["diagnostics"]) == 2
        assert {row["time_basis"]["basis"] for row in raw["charts"]} == {
            "true_solar",
            "standard",
            "beijing_standard",
        }


def test_rules_are_true_only_and_all_38_assessments_remain(originals: dict) -> None:
    preview = originals["bazi"]
    hits = [value(preview, ref) for ref in preview["view"]["rules"]]
    assert len(hits) == len(preview["aliases"]["r"]) == 9
    assert all(row["met"] is True for row in hits)
    assessments = value(preview, preview["view"]["assessments"][0])
    assert len(assessments) == 38
    assert any(row["met"] is False for row in assessments)
    assert all(row["basis"] == "true_solar" for row in preview["aliases"]["r"])


def test_ziwei_full_flying_and_unavailable_temporal_layers_are_preserved(
    originals: dict,
) -> None:
    preview = originals["ziwei"]
    flying = value(preview, preview["view"]["flying"][0])
    assert len(flying["edges"]) == 48
    assert all(
        row["status"] == "unavailable" and row["links"] == []
        for row in flying["temporal_layers"].values()
    )
    assert preview["aliases"]["r"] == []


def test_astro_has_real_windows_and_both_named_timings(originals: dict) -> None:
    preview = originals["astro"]
    transits = value(preview, preview["view"]["transits"][0])
    assert len(transits["windows"]) == 20
    assert set(transits["returned_flags"]) == {"月亮", "太阳"}
    timings = [value(preview, ref) for ref in preview["view"]["timings"]]
    assert {row["version"] for row in timings} == {
        "p8-secondary-progressions-v1",
        "p8-solar-return-v1",
    }
    assert all(
        utc(row["actual_UTC"]["birth_at"]) == utc("1994-03-12T00:20:00Z")
        for row in timings
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("revision", -1),
        ("revision", True),
        ("operation_id", ""),
        ("owner_user_id", "foreign"),
    ],
)
def test_scope_rejections(originals: dict, field: str, bad) -> None:
    preview = deepcopy(originals["bazi"])
    preview["scope"][field] = bad
    with pytest.raises(ValueError):
        validate_preview(preview)


@pytest.mark.parametrize(
    "mutation",
    [
        "doc_id",
        "value_hash",
        "claim_id",
        "alias_scope",
        "basis",
        "branch",
        "rule_version",
        "evidence",
        "dangling",
    ],
)
def test_claim_and_reference_tampering_is_rejected(
    originals: dict, mutation: str
) -> None:
    preview = deepcopy(originals["bazi"])
    chart = preview["aliases"]["c"][0]
    rule = preview["aliases"]["r"][0]
    if mutation == "doc_id":
        preview["documents"][0]["document_id"] = "doc-" + "0" * 64
    elif mutation == "value_hash":
        chart["value_sha256"] = "0" * 64
    elif mutation == "claim_id":
        chart["claim_id"] = "demo-claim-" + "0" * 64
    elif mutation == "alias_scope":
        chart["scope"]["subject_id"] = "foreign"
    elif mutation in ("basis", "branch"):
        rule["basis" if mutation == "basis" else "branch_id"] = (
            "standard" if mutation == "basis" else "foreign"
        )
        rule["claim_id"] = claim_id(rule)
    elif mutation == "rule_version":
        rule["rules_version"] = "made-up"
        rule["claim_id"] = claim_id(rule)
    elif mutation == "evidence":
        rule["evidence_aliases"] = [chart["alias"]]
    else:
        preview["view"]["primary"][0]["document_id"] = "doc-" + "0" * 64
    with pytest.raises(ValueError):
        validate_preview(preview)


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_primary_cannot_be_removed(originals: dict, system: str) -> None:
    preview = deepcopy(originals[system])
    preview["view"]["primary"] = []
    with pytest.raises(ValueError):
        validate_preview(preview)


def test_dropping_all_rules_and_r_aliases_does_not_hide_hits(originals: dict) -> None:
    preview = deepcopy(originals["bazi"])
    preview["view"]["rules"] = []
    preview["aliases"]["r"] = []
    with pytest.raises(ValueError, match="basis_view"):
        validate_preview(preview)


def test_false_assessment_cannot_be_promoted_to_r_alias(originals: dict) -> None:
    preview = deepcopy(originals["bazi"])
    doc = preview["documents"][0]
    primary = preview["view"]["primary"][0]["path"]
    rows = resolve(doc["payload"], primary + "/p8/rule_assessments")
    index = next(i for i, row in enumerate(rows) if row["met"] is False)
    rule = preview["aliases"]["r"][0]
    rule["ref"]["path"] = primary + f"/p8/rule_assessments/{index}"
    rule["value_sha256"] = digest(rows[index])
    rule["claim_id"] = claim_id(rule)
    with pytest.raises(ValueError, match="true_hit"):
        validate_preview(preview)


def test_timing_cannot_use_true_solar_coordinate_as_actual_utc(originals: dict) -> None:
    preview = deepcopy(originals["astro"])
    doc = next(row for row in preview["documents"] if row["kind"] == "western_timing")
    doc["payload"]["data"]["actual_UTC"]["birth_at"] = "1994-03-11T23:04:00Z"
    rebind(preview, doc)
    with pytest.raises(ValueError, match="birth_utc"):
        validate_preview(preview)


def test_native_scope_is_checked_even_after_validly_rehashing_document(
    originals: dict,
) -> None:
    preview = deepcopy(originals["bazi"])
    doc = preview["documents"][0]
    doc["payload"]["subject_id"] = "foreign"
    rebind(preview, doc)
    with pytest.raises(ValueError, match="scope_mismatch"):
        validate_preview(preview)


@pytest.mark.parametrize("view", ["flying", "timings", "transits"])
def test_calculation_detail_views_cannot_be_removed(originals: dict, view: str) -> None:
    preview = deepcopy(originals["ziwei" if view == "flying" else "astro"])
    preview["view"][view] = []
    with pytest.raises(ValueError):
        validate_preview(preview)


@pytest.mark.parametrize("mutation", ["date", "utc", "nan", "live", "extra"])
def test_structure_and_finite_json_guards(originals: dict, mutation: str) -> None:
    preview = deepcopy(originals["bazi"])
    if mutation == "date":
        preview["request"]["target_date"] = "2026-02-30"
    elif mutation == "utc":
        preview["request"]["physical_birth_at_utc"] = "1994-03-12T00:20:00"
    elif mutation == "nan":
        preview["request"]["birth"]["place"]["lon"] = float("nan")
    elif mutation == "live":
        preview["mode"] = "live"
    else:
        preview["effects"]["saved_to_database"] = True
    with pytest.raises(ValueError):
        validate_preview(preview)


@pytest.mark.parametrize("kind", ["time_basis", "calculation_bundle", "western_timing"])
def test_source_native_hash_binding_rejects_rehashed_sidecar(
    originals: dict, kind: str
) -> None:
    preview = deepcopy(originals["astro"])
    doc = next(row for row in preview["documents"] if row["kind"] == kind)
    key = next(iter(doc["source_sha256"]))
    doc["source_sha256"][key] = "0" * 64
    rebind(preview, doc)
    with pytest.raises(ValueError, match="source"):
        validate_preview(preview)


@pytest.mark.parametrize(
    "path", ["/a/-1", "/a/01", "/a/+1", "/a/1.0", "/a/9", "/bad~2escape"]
)
def test_pointer_indices_and_escapes_are_strict(path: str) -> None:
    with pytest.raises(ValueError):
        resolve({"a": [10, 20]}, path)
    assert resolve({"a/b": {"~key": 1}}, "/a~1b/~0key") == 1


def test_claim_ids_do_not_depend_on_ephemeral_short_alias_numbers(
    originals: dict,
) -> None:
    preview = deepcopy(originals["bazi"])
    before = [row["claim_id"] for row in preview["aliases"]["r"]]
    names = {
        row["alias"]: f"c{i}"
        for i, row in enumerate(reversed(preview["aliases"]["c"]), 1)
    }
    preview["aliases"]["c"].reverse()
    for index, row in enumerate(preview["aliases"]["c"], 1):
        row["alias"] = f"c{index}"
    for row in preview["aliases"]["r"]:
        row["evidence_aliases"] = [names[name] for name in row["evidence_aliases"]]
    validate_preview(preview)
    assert [row["claim_id"] for row in preview["aliases"]["r"]] == before


def test_offline_transport_rejects_network_and_restores_process_state(
    monkeypatch,
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "synthetic-key-never-sent")
    original = socket.create_connection
    with offline_runtime():
        assert "KIMI_API_KEY" not in os.environ
        assert os.environ["LANGSMITH_TRACING"] == "false"
        with pytest.raises(RuntimeError, match="network_transport_disabled"):
            socket.create_connection(("example.invalid", 443))
    assert socket.create_connection is original
    assert os.environ["KIMI_API_KEY"] == "synthetic-key-never-sent"

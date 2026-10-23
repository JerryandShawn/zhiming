"""Learning cards reuse real aliases; tampering cannot create a teaching fact."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import claim_id
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.learning import learning_outline

ROOT = Path(__file__).resolve().parents[2]


def preview(system: str = "bazi") -> dict:
    path = ROOT / f"docs/v4/contracts/samples/ayuan_{system}.json"
    return json.loads(path.read_text(encoding="utf8"))


@pytest.mark.parametrize("system", ["bazi", "ziwei", "astro"])
def test_actual_three_systems_use_only_existing_current_aliases(system: str) -> None:
    source = preview(system)
    before = deepcopy(source)
    result = learning_outline(source)
    assert result == learning_outline(source) and source == before
    assert (
        result["points"]
        and result["effects"]["model_calls"] == result["effects"]["writes"] == 0
    )
    names = {row["alias"]: row for group in source["aliases"].values() for row in group}
    for point in result["points"]:
        assert point["school"] and point["source_refs"] and point["source_ref"]
        for name in point["c_aliases"] + point["r_aliases"]:
            assert name in names and "〔" + name + "〕" in point["citations"]
    for key, rows in result["aliases"].items():
        assert all(row in source["aliases"][key] for row in rows)
    assert all(hit["met"] is True for hit in result["rule_hits"])


def test_day_master_is_from_actual_chart_not_a_personality_template() -> None:
    result = learning_outline(preview())
    assert result["points"][0]["observed"]["ganzhi"] == "丁酉"
    assert "日干丁" in result["points"][0]["text"]
    condition = next(
        row for row in result["points"] if row["kind"] == "matched_condition"
    )
    assert condition["observed"] and "单项满足" in condition["text"]


@pytest.mark.parametrize("system", ["ziwei", "astro"])
def test_real_boundary_comes_from_input_rule_not_a_fabricated_warning(
    system: str,
) -> None:
    result = learning_outline(preview(system))
    warning = next(row for row in result["points"] if row["kind"] == "boundary")
    assert len(warning["observed"]["alternatives"]) == 2
    assert warning["r_aliases"] and "倒推" in warning["text"]


@pytest.mark.parametrize("limit", [0, 31, True, 2.5, "3", None])
def test_invalid_limits_are_rejected(limit) -> None:
    with pytest.raises(ValueError, match="learning_limit_invalid"):
        learning_outline(preview(), limit=limit)


def test_limit_one_keeps_only_evidence_used_by_visible_orientation() -> None:
    source = preview()
    result = learning_outline(source, limit=1)
    assert len(result["points"]) == 1 and not result["rule_hits"]
    assert len(result["aliases"]["c"]) == 1 and result["aliases"]["r"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        "payload",
        "doc_id",
        "claim",
        "scope",
        "false",
        "nan",
        "pointer",
        "evidence",
        "branch",
    ],
)
def test_mutated_reference_content_cannot_become_a_learning_card(mutation: str) -> None:
    source = preview()
    row = source["aliases"]["r"][0]
    if mutation == "payload":
        source["documents"][0]["payload"]["charts"][0]["data"]["pillars"]["day"][
            "gan"
        ] = "甲"
    elif mutation == "doc_id":
        source["documents"][0]["document_id"] = "doc-" + "0" * 64
    elif mutation == "claim":
        row["claim_id"] = "demo-claim-" + "0" * 64
    elif mutation == "scope":
        source["scope"]["owner_user_id"] = "foreign"
    elif mutation == "nan":
        source["request"]["birth"]["place"]["lon"] = float("nan")
    elif mutation == "pointer":
        source["view"]["primary"][0]["path"] = "/charts/00/data"
    elif mutation == "evidence":
        row["evidence_aliases"] = [source["aliases"]["c"][0]["alias"]]
    elif mutation == "branch":
        row["branch_id"] = "foreign-branch"
        row["claim_id"] = claim_id(row)
    else:
        raw = source["documents"][0]["payload"]
        items = raw["charts"][0]["data"]["p8"]["rule_assessments"]
        index = next(index for index, item in enumerate(items) if item["met"] is False)
        row["ref"]["path"] = f"/charts/0/data/p8/rule_assessments/{index}"
        row["value_sha256"] = content_hash(pointer(raw, row["ref"]["path"]))
        row["claim_id"] = claim_id(row)
    with pytest.raises(ValueError):
        learning_outline(source)


def test_display_name_is_not_a_hardcoded_fixture_filter() -> None:
    source = preview()
    source["display_name"] = "另一个调用方标题"
    assert learning_outline(source)["points"]


def test_unsupported_contract_and_scope_types_are_rejected() -> None:
    source = preview()
    source["contract_version"] = "unknown"
    with pytest.raises(ValueError, match="unsupported"):
        learning_outline(source)
    source = preview()
    source["scope"]["revision"] = True
    with pytest.raises(ValueError, match="scope_invalid"):
        learning_outline(source)

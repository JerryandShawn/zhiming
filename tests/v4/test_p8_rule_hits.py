"""U12 true/false fixtures, honest source scope and deterministic U2 ordering."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from p8_rules_sample_context import make_data

from mingjing_core.adapters.charts.interactions_bazi import bazi_interactions
from mingjing_core.adapters.charts.rules import (
    evaluate_rules,
    load_registry,
    validate_registry,
)

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads(
    (Path(__file__).with_name("fixtures") / "p8_rule_cases.json").read_text(
        encoding="utf-8"
    )
)["cases"]


def resolve(value: dict, path: str) -> object:
    current = value
    for part in path.split("/")[1:]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


@pytest.mark.parametrize("rule_id", sorted(CASES))
@pytest.mark.parametrize("label,expected", [("positive", True), ("negative", False)])
def test_every_rule_has_an_independent_pillar_positive_and_negative(
    rule_id: str, label: str, expected: bool
) -> None:
    case = CASES[rule_id][label]
    data = make_data(case["pillars"], case["layers"])
    before = deepcopy(data)
    result = evaluate_rules(data)
    row = next(item for item in result["assessments"] if item["rule_id"] == rule_id)
    assert row["met"] is expected
    assert (rule_id in {item["rule_id"] for item in result["rule_hits"]}) is expected
    assert len(result["assessments"]) == 35
    assert all(item["met"] is True for item in result["rule_hits"])
    assert data == before
    for path in row["evidence_paths"]:
        resolve({"data": data}, path)


def test_all_35_rules_have_reviewable_metadata_and_no_interpretation_result() -> None:
    registry = load_registry()
    validate_registry(registry)
    assert len(registry["rules"]) == 35 <= 40
    assert set(CASES) == {row["rule_id"] for row in registry["rules"]}
    for row in registry["rules"]:
        assert (
            row["source"] is not None
            and row["source"]["book"]
            and row["source"]["chapter"]
        )
        assert row["claim_kind"] == "traditional"
        assert "interpretation" not in row and "prediction" not in row


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "too_many", "priority", "condition", "path", "claim", "params"],
)
def test_registry_rejects_invalid_schemas(mutation: str) -> None:
    value = load_registry()
    if mutation == "duplicate":
        value["rules"][1]["rule_id"] = value["rules"][0]["rule_id"]
    elif mutation == "too_many":
        value["rules"] *= 2
    elif mutation == "priority":
        value["rules"][0]["priority"]["子平"] = True
    elif mutation == "condition":
        value["rules"][0]["condition_ref"] = "exec"
    elif mutation == "path":
        value["rules"][0]["evidence_fields"] = ["../../private"]
    elif mutation == "claim":
        value["rules"][0]["claim_kind"] = "verified_prediction"
    else:
        value["rules"][0]["parameters"]["condition_index"] = True
    with pytest.raises(ValueError):
        validate_registry(value)


@pytest.mark.parametrize("school", ["子平", "调候", "盲派", "通用"])
def test_u2_labels_and_sorting_are_explicit_and_stable_by_school(school: str) -> None:
    case = CASES["u12-palace-day-clash-combine"]["positive"]
    first = bazi_interactions(case["pillars"], case["layers"], school=school)
    second = bazi_interactions(
        dict(reversed(list(case["pillars"].items()))), case["layers"], school=school
    )
    assert json.dumps(first, ensure_ascii=False) == json.dumps(
        second, ensure_ascii=False
    )
    priorities = [row["priority"][school] for row in first["relations"]]
    assert priorities == sorted(priorities)
    for row in first["relations"]:
        expected = [
            key
            for key in ("year", "month", "day", "hour")
            if any(member["id"] == "natal." + key for member in row["members"])
        ]
        assert row["palace"] == expected
        assert set(row["priority"]) == {"子平", "调候", "盲派", "通用"}
        assert row["mapping_status"] == "project_convention_v1_not_expert_calibrated"
        assert row["domains"]


def test_graph_override_is_not_silently_ignored() -> None:
    case = CASES["u12-palace-day-clash-combine"]["positive"]
    data = make_data(case["pillars"], case["layers"])
    result = evaluate_rules(data, graph={"relations": []})
    assert not any(
        item["rule_id"].startswith("u12-palace-") for item in result["rule_hits"]
    )
    assert "supplied graph" in result["graph_binding"]


def test_three_public_textbook_charts_match_full_condition_snapshots() -> None:
    path = ROOT / "docs/v4/evidence/P8/rules-public-snapshots.json"
    snapshots = json.loads(path.read_text(encoding="utf-8"))
    assert len(snapshots["charts"]) == 3
    for chart in snapshots["charts"]:
        actual = evaluate_rules(make_data(chart["pillars"]))
        assert actual["assessments"] == chart["assessments"]
        assert [row["rule_id"] for row in actual["rule_hits"]] == chart["hit_ids"]
        assert chart["source"]["url"].startswith("https://")

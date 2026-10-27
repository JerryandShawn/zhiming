"""Reachable condition contrasts on legal independent pillars, not birth records."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from p8_rules_sample_context import make_data

from mingjing_core.adapters.charts.rules import evaluate_rules, load_registry
from mingjing_core.adapters.charts.tool_evidence import evidence_result, pointer

BASE_LU = {"year": "辛酉", "month": "戊寅", "day": "甲子", "hour": "壬申"}
BASE_ROBBER = {"year": "庚申", "month": "戊寅", "day": "乙丑", "hour": "癸亥"}
BASE_BLADE = {"year": "辛酉", "month": "己卯", "day": "甲子", "hour": "壬申"}
RULES = {
    "建禄": "u12-pattern-established-lu",
    "月劫": "u12-pattern-month-robber",
    "阳刃": "u12-pattern-yang-blade",
}
PAIRS = [
    ("建禄", 0, BASE_LU, dict(BASE_LU, month="戊辰")),
    ("建禄", 1, BASE_LU, dict(BASE_LU, year="壬申")),
    (
        "建禄",
        2,
        {"year": "庚申", "month": "丙寅", "day": "甲子", "hour": "丙申"},
        {"year": "庚申", "month": "丙寅", "day": "甲子", "hour": "壬申"},
    ),
    ("月劫", 0, BASE_ROBBER, dict(BASE_ROBBER, month="戊辰")),
    ("月劫", 1, BASE_ROBBER, dict(BASE_ROBBER, year="癸亥")),
    (
        "月劫",
        2,
        {"year": "庚申", "month": "壬寅", "day": "乙丑", "hour": "丁卯"},
        {"year": "辛酉", "month": "壬寅", "day": "乙丑", "hour": "丁卯"},
    ),
    ("阳刃", 0, BASE_BLADE, dict(BASE_BLADE, month="己巳")),
    ("阳刃", 1, BASE_BLADE, dict(BASE_BLADE, year="癸酉")),
    ("阳刃", 2, BASE_BLADE, dict(BASE_BLADE, hour="丁卯")),
]
PAIR_IDS = [f"{RULES[name]}-condition-{index + 1}" for name, index, _, _ in PAIRS]


def _digest(value: object) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf8")).hexdigest()


def _observe(name: str, pillars: dict) -> tuple[dict, dict, dict, list]:
    before_pillars = deepcopy(pillars)
    data = make_data(pillars)
    before_data = deepcopy(data)
    evaluated = evaluate_rules(data)
    row = next(
        item
        for item in data["p8"]["patterns"]["regular_extra"]
        if item["pattern"] == name + "格"
    )
    assessment = next(
        item for item in evaluated["assessments"] if item["rule_id"] == RULES[name]
    )
    hits = [item for item in evaluated["rule_hits"] if item["rule_id"] == RULES[name]]
    assert pillars == before_pillars
    assert data == before_data
    assert data["p8"]["patterns"]["establishment"] == "candidate_only"
    assert assessment["details"]["scope"] == (
        "three_explicit_candidate_conditions_not_established_pattern"
    )
    return data, row, assessment, hits


def _check_evidence(data: dict, row: dict, assessment: dict, hits: list) -> None:
    conditions = row["conditions"]
    paths = assessment["evidence_paths"]
    assert len(paths) == len(set(paths)) == len(conditions) == 3
    for path, condition in zip(paths, conditions, strict=True):
        assert pointer({"data": data}, path) == condition
        assert type(condition["satisfied"]) is bool
    assert assessment["details"]["condition_assessments"] == conditions
    assert assessment["met"] is row["screen_passed"]
    assert len(hits) == int(assessment["met"])
    if hits:
        assert hits[0] == assessment
    registry_row = next(
        item
        for item in load_registry()["rules"]
        if item["rule_id"] == assessment["rule_id"]
    )
    assert assessment["source"] == registry_row["source"]
    assert assessment["condition_ref"] == "extra_pattern"
    assert assessment["source"]["book"] and assessment["source"]["chapter"]


def _check_ephemeral_aliases(data: dict, assessment: dict, hits: list) -> None:
    # A test-local tool envelope, not a chart_compute or persistent ledger claim.
    before = deepcopy((data, assessment, hits))
    result = evidence_result(
        "p8-extra-condition-test-fixture-v1",
        data,
        hits,
        [assessment["source"]],
    )
    assert (data, assessment, hits) == before
    assert result["scope"] is None
    assert result["effects"]["alias_registry"] == "ephemeral_only"
    assert len(result["aliases"]["r"]) == len(hits)
    if not hits:
        assert not result["aliases"]["c"]
        return
    rule_alias = result["aliases"]["r"][0]
    assert pointer(result, rule_alias["path"]) == hits[0]
    assert rule_alias["value_sha256"] == _digest(hits[0])
    assert rule_alias["rule_id"] == assessment["rule_id"]
    charts = {item["alias"]: item for item in result["aliases"]["c"]}
    assert len(rule_alias["evidence_aliases"]) == 3
    assert set(charts) == set(rule_alias["evidence_aliases"])
    for name in rule_alias["evidence_aliases"]:
        alias = charts[name]
        assert alias["path"] in assessment["evidence_paths"]
        assert alias["value_sha256"] == _digest(pointer(result, alias["path"]))


@pytest.mark.parametrize("name,index,positive,negative", PAIRS, ids=PAIR_IDS)
def test_single_pillar_change_independently_controls_each_condition(
    name: str, index: int, positive: dict, negative: dict
) -> None:
    before = deepcopy((positive, negative))
    assert set(positive) == set(negative) == {"year", "month", "day", "hour"}
    assert sum(positive[key] != negative[key] for key in positive) == 1
    observed = []
    for expected, pillars in ((True, positive), (False, negative)):
        data, row, assessment, hits = _observe(name, pillars)
        assert row["screen_passed"] is expected
        assert assessment["met"] is expected
        _check_evidence(data, row, assessment, hits)
        _check_ephemeral_aliases(data, assessment, hits)
        observed.append([item["satisfied"] for item in row["conditions"]])
    expected_negative = [True, True, True]
    expected_negative[index] = False
    assert observed == [[True, True, True], expected_negative]
    assert sum(left != right for left, right in zip(*observed, strict=True)) == 1
    assert (positive, negative) == before


@pytest.mark.parametrize("name", sorted(RULES))
def test_each_registered_extra_pattern_has_three_separate_contrasts(name: str) -> None:
    rows = [item for item in PAIRS if item[0] == name]
    assert sorted(item[1] for item in rows) == [0, 1, 2]
    assert len(rows) == 3
    registered = [
        row for row in load_registry()["rules"] if row["rule_id"] == RULES[name]
    ]
    assert len(registered) == 1
    assert registered[0]["condition_ref"] == "extra_pattern"
    assert registered[0]["parameters"] == {"pattern": name}

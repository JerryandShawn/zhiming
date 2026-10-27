"""Reviewed conditions protect P8 changes and the unchanged v3 behavior."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from p8_rules_sample_context import make_data

from mingjing_core.adapters.charts.named_bazi import hidden_for, options
from mingjing_core.adapters.charts.named_strength import named_patterns, named_scores
from mingjing_core.adapters.charts.p8_structure import reviewed_regular, reviewed_useful
from mingjing_core.adapters.charts.rules import evaluate_rules, load_registry, validate_registry
from mingjing_core.adapters.charts.rules.conditions import pattern_condition
from mingjing_core.calculations.bazi.elements import table
from mingjing_core.calculations.bazi.structure import AVOID, PATTERN_SUPPORT
from mingjing_core.domain.json_values import ensure_finite_json

HIDDEN = hidden_for(options())
REVIEW_CASES = json.loads((Path(__file__).with_name("fixtures") / "p8_rule_cases.json").read_text(encoding="utf8"))[
    "review_counterexamples"
]


def c3(pillars: dict[str, str], god: str) -> dict:
    return next(row for row in reviewed_regular(pillars, HIDDEN) if row["ten_god"] == god)["conditions"][2]


@pytest.mark.parametrize("case", REVIEW_CASES, ids=[row["name"] for row in REVIEW_CASES])
def test_required_review_counterexample_fixtures(case: dict) -> None:
    row = next(
        row for row in evaluate_rules(make_data(case["pillars"]))["assessments"] if row["rule_id"] == case["rule_id"]
    )
    assert row["met"] is case["expected"]
    assert row["details"]["observed"]["metal_water_exception"] is case.get("exception", False)


def test_hurting_officer_with_killer_remains_candidate_and_officer_blocks() -> None:
    # Independent valid stem/branch pairs, not a purported calendrical birth.
    pillars = {"year": "丁卯", "month": "庚午", "day": "甲子", "hour": "壬申"}
    assert c3(pillars, "伤官")["satisfied"]
    assert not c3(dict(pillars, month="辛未"), "伤官")["satisfied"]
    assert AVOID["伤官"] == "七杀"  # Legacy kept byte-for-byte; P8 overrides explicitly.


@pytest.mark.parametrize("day,hour", [("庚子", "丁卯"), ("辛丑", "丙寅")])
def test_metal_day_master_officer_exception_is_visible(day: str, hour: str) -> None:
    pillars = {"year": "壬子", "month": "癸亥", "day": day, "hour": hour}
    condition = c3(pillars, "伤官")
    assert condition["satisfied"]
    assert condition["evidence"]["metal_water_exception"]
    combo = next(
        row
        for row in evaluate_rules(make_data(pillars))["assessments"]
        if row["rule_id"] == "u12-combo-hurting-officer-officer"
    )
    assert combo["met"]
    assert combo["details"]["metal_water_exception"]


@pytest.mark.parametrize("wealth", ["戊辰", "己巳"])
def test_killer_both_wealths_block_only_without_exposed_food(wealth: str) -> None:
    pillars = {"year": wealth, "month": "庚午", "day": "甲子", "hour": "壬申"}
    assert not c3(pillars, "七杀")["satisfied"]
    assert c3(dict(pillars, hour="丙寅"), "七杀")["satisfied"]
    assert c3(pillars, "七杀")["evidence"]["not_evaluated"]


@pytest.mark.parametrize("god", ["正印", "偏印"])
@pytest.mark.parametrize("wealth", ["戊辰", "己巳"])
def test_both_seals_screen_both_wealths_without_claiming_light_seal(god: str, wealth: str) -> None:
    pillars = {"year": wealth, "month": "壬子", "day": "甲子", "hour": "癸亥"}
    row = c3(pillars, god)
    assert not row["satisfied"]
    assert "印轻前提未判" in row["evidence"]["not_evaluated"][0]


@pytest.mark.parametrize("god", ["正财", "偏财"])
@pytest.mark.parametrize("restraint", ["甲寅", "乙卯", "庚申"])
def test_both_wealths_screen_both_peers_and_killer(god: str, restraint: str) -> None:
    pillars = {"year": restraint, "month": "戊辰", "day": "甲子", "hour": "壬申"}
    assert not c3(pillars, god)["satisfied"]


def test_month_hidden_roles_rank_filter_and_mixed_qi_note() -> None:
    pillars = {"year": "壬辰", "month": "戊辰", "day": "甲子", "hour": "庚午"}
    data = make_data(pillars)
    params = {"god": "偏财", "condition_index": 0}
    hit = pattern_condition(data, dict(params, qi_rank="本气"), {})
    miss = pattern_condition(data, dict(params, qi_rank="余气"), {})
    assert hit["met"] and not miss["met"]
    assert hit["details"]["qi_matches"] == [{"stem": "戊", "ten_god": "偏财", "qi_rank": 0, "role": "本气"}]
    assert "第十六章" in hit["details"]["notes"][0]
    registry = load_registry()
    registry["rules"][0]["parameters"]["qi_rank"] = "神秘气"
    with pytest.raises(ValueError, match="气位"):
        validate_registry(registry)


def test_three_extra_candidates_have_three_transparent_conditions() -> None:
    cases = [
        ("建禄", {"year": "辛酉", "month": "戊寅", "day": "甲子", "hour": "壬申"}),
        ("月劫", {"year": "庚申", "month": "戊寅", "day": "乙丑", "hour": "癸亥"}),
        ("阳刃", {"year": "辛酉", "month": "己卯", "day": "甲子", "hour": "壬申"}),
    ]
    for name, pillars in cases:
        row = next(
            item for item in make_data(pillars)["p8"]["patterns"]["regular_extra"] if item["pattern"] == name + "格"
        )
        assert row["screen_passed"]
        assert len(row["conditions"]) == 3
        assert not row["unsatisfied"]


@pytest.mark.parametrize(
    "name,pillars,expected",
    [
        ("建禄", {"year": "庚申", "month": "壬寅", "day": "甲子", "hour": "癸亥"}, [True, False, False]),
        ("月劫", {"year": "辛酉", "month": "壬寅", "day": "乙丑", "hour": "癸亥"}, [True, False, False]),
        ("阳刃", {"year": "辛酉", "month": "己卯", "day": "甲子", "hour": "丁卯"}, [True, True, False]),
        ("阳刃", {"year": "甲子", "month": "己卯", "day": "甲子", "hour": "丙寅"}, [True, False, True]),
        ("阳刃", {"year": "甲子", "month": "己巳", "day": "乙丑", "hour": "丙寅"}, [False, False, False]),
    ],
)
def test_extra_conditions_keep_missing_path_and_explicit_failure_separate(
    name: str, pillars: dict, expected: list[bool]
) -> None:
    row = next(row for row in make_data(pillars)["p8"]["patterns"]["regular_extra"] if row["pattern"] == name + "格")
    assert [item["satisfied"] for item in row["conditions"]] == expected
    assert not row["screen_passed"]


def test_killer_support_adds_seals_without_mutating_legacy() -> None:
    pillars = {"year": "壬辰", "month": "庚申", "day": "甲子", "hour": "癸亥"}
    strength = named_scores(pillars, HIDDEN)
    pattern = named_patterns(pillars, HIDDEN, strength)
    before = deepcopy(PATTERN_SUPPORT)
    result = reviewed_useful(pillars, strength, pattern, table("climate")["rows"]["甲申"])
    ensure_finite_json(result)
    assert all(isinstance(values, list) for values in result["pattern_support"].values())
    row = next(row for row in result["pattern"] if row["pattern"] == "七杀格")
    assert row["candidate_ten_gods"] == ["食神", "正印", "偏印"]
    assert before == PATTERN_SUPPORT and PATTERN_SUPPORT["七杀"] == ("食神",)


def test_climate_details_keep_exposed_and_only_hidden_separate() -> None:
    pillars = {"year": "甲子", "month": "丙寅", "day": "甲辰", "hour": "辛未"}
    row = next(
        row
        for row in evaluate_rules(make_data(pillars))["assessments"]
        if row["rule_id"] == "u12-climate-candidate-missing"
    )
    assert row["source"]["book"] == "穷通宝鉴"
    details = row["details"]
    assert not set(details["exposed_candidate_stems"]) & set(details["hidden_only_candidate_stems"])
    assert set(details["hidden_only_candidate_stems"]) <= set(details["not_exposed_candidate_stems"])

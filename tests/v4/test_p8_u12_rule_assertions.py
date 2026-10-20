"""All 38 current IDs/names have affirmative and negative assertion cases."""

from __future__ import annotations

from copy import deepcopy

import pytest
from p8_u12_assertions_context import RULES, TRUE_IDS, native, preview

from mingjing_core.skills.consistency_u12 import check_u12_rule_assertions
from mingjing_core.skills.consistency_u12_input import SHORT_NAMES


@pytest.fixture(scope="module")
def chart() -> dict:
    return preview()


def one(text: str, chart: dict) -> dict:
    result = check_u12_rule_assertions(text, chart)
    assert len(result["data"]["checks"]) == 1
    return result["data"]["checks"][0]


@pytest.mark.parametrize("rule", RULES, ids=lambda row: row["rule_id"])
@pytest.mark.parametrize(
    "claimed", [True, False], ids=["claimed-hit", "claimed-no-hit"]
)
def test_all_current_rule_ids_compare_actual_boolean_without_claiming_effectiveness(
    chart: dict, rule: dict, claimed: bool
) -> None:
    key = rule["rule_id"]
    text = f"规则[{key}]条件" + ("命中" if claimed else "未命中")
    row = one(text, chart)
    actual = key in TRUE_IDS
    assert row["outcome"] == ("matched" if claimed == actual else "contradiction")
    assert row["expected_values"] == [actual]
    assert row["assertion"]["key"] == key
    assert row["assessments"][0]["name"] == rule["name"]
    assert row["assessments"][0]["met"] is actual
    assert row["source_refs"][0]["path"].endswith("/met")
    assert row["input_c_aliases"] and row["fact_sources"][0]["source"]
    assert bool(row["input_r_aliases"]) is actual


@pytest.mark.parametrize("rule", RULES, ids=lambda row: row["rule_id"])
@pytest.mark.parametrize(
    "bracketed", [True, False], ids=["native-name-in-brackets", "native-name"]
)
def test_all_names_including_slash_semicolon_and_negative_condition_labels_stay_identifiers(
    chart: dict, rule: dict, bracketed: bool
) -> None:
    label = f"规则[{rule['name']}]" if bracketed else rule["name"]
    actual = rule["rule_id"] in TRUE_IDS
    row = one(label + "条件" + ("命中" if actual else "未命中"), chart)
    assert row["outcome"] == "matched"
    assert row["assessments"][0]["rule_id"] == rule["rule_id"]
    assert row["span"] == {"start": 0, "end": len(label) + (4 if actual else 5)}


@pytest.mark.parametrize("name,key", SHORT_NAMES.items())
@pytest.mark.parametrize(
    "operator,claimed",
    [
        ("这是", True),
        ("是", True),
        ("不是", False),
        ("并非", False),
        ("没有出现", False),
        ("出现", True),
        ("这不是", False),
        ("这并非", False),
    ],
)
def test_five_explicit_short_names_refer_only_to_coappearance_conditions(
    chart: dict, name: str, key: str, operator: str, claimed: bool
) -> None:
    row = one("你" + operator + name, chart)
    assert row["assertion"]["key"] == key
    assert row["outcome"] == (
        "matched" if (key in TRUE_IDS) == claimed else "contradiction"
    )
    assert (
        row["assessments"][0]["condition_scope"]
        == "exposed_coappearance_not_effectiveness"
    )
    assert "不授权" in row["assessments"][0]["meaning"]


@pytest.mark.parametrize("name,key", SHORT_NAMES.items())
def test_short_name_requires_an_assertion_and_bare_term_is_deferred(
    chart: dict, name: str, key: str
) -> None:
    assert one(name, chart)["reason_code"] == "u12_assertion_not_explicit"
    assert one(f"规则[{name}]条件未命中", chart)["assertion"]["key"] == key


@pytest.mark.parametrize(
    "text",
    [
        "枭神夺食条件命中",
        "食神制杀条件命中",
        "伤官配印条件命中",
        "完整夺食成立",
        "规则[u12-combo-output-killer]条件命中且制杀有效",
        "你已经成格",
        "规则[u12-pattern-yang-blade]条件命中并说明已经成格",
        "食神制杀有效",
    ],
)
def test_condition_flags_never_authorize_complete_effectiveness_or_established_patterns(
    chart: dict, text: str
) -> None:
    result = check_u12_rule_assertions(text, chart)
    assert result["data"]["status"] == "needs_review"
    assert not any(
        row["outcome"] in ("matched", "contradiction")
        for row in result["data"]["checks"]
    )


def test_input_is_unchanged_deterministic_and_unknown_freeform_text_is_not_echoed(
    chart: dict,
) -> None:
    source = deepcopy(chart)
    before = deepcopy(source)
    answer = "私人生活正文。规则[未知私密名字]条件命中。你这是伤官见官。"
    result = check_u12_rule_assertions(answer, source, expected_scope=source["scope"])
    assert result == check_u12_rule_assertions(
        answer, source, expected_scope=source["scope"]
    )
    assert (
        source == before
        and result["effects"]["model_calls"] == result["effects"]["writes"] == 0
    )
    assert "私人生活正文" not in str(result) and "未知私密名字" not in str(result)
    assert result["data"]["status"] == "inconsistent"


def test_expected_truth_table_is_the_actual_unchanged_ayuan_assessment_not_a_parser_fixture(
    chart: dict,
) -> None:
    rows = native(chart)["rule_assessments"]
    assert len(rows) == 38
    assert {row["rule_id"] for row in rows if row["met"]} == TRUE_IDS

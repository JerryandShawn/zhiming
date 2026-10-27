"""False carriers, ambiguous identifiers and invalid citations cannot become proof."""

from __future__ import annotations

from copy import deepcopy

import pytest
from p8_u12_assertions_context import TRUE_IDS, native, preview, rehash, root_alias

from mingjing_core.skills.consistency_u12 import check_u12_rule_assertions

FALSE_ID = "u12-combo-hurting-officer-officer"
TRUE_ID = "u12-pattern-seal-c2"


def outcome(chart: dict, text: str) -> dict:
    result = check_u12_rule_assertions(text, chart)
    return result["data"]["checks"][0]


@pytest.mark.parametrize(
    "text,reason",
    [
        (f"如果规则[{FALSE_ID}]条件命中", "hypothetical"),
        (f"规则[{FALSE_ID}]条件命中？", "question"),
        (f"不是不规则[{FALSE_ID}]条件命中", "complex_negation"),
        (f"“规则[{FALSE_ID}]条件命中”", "quoted_or_reported"),
        (f"规则[{FALSE_ID}]条件命中，才怪", "complex_negation"),
        (f"规则[{FALSE_ID}]条件命中，这个说法不成立", "complex_negation"),
        (f"北京时间规则[{FALSE_ID}]条件命中", "comparison_basis"),
        (f"小禾的命盘如下。\n规则[{FALSE_ID}]条件命中", "other_subject"),
        (f"旧盘结果：\n规则[{FALSE_ID}]条件命中", "other_layer"),
        (f"规则[{FALSE_ID}]条件命中，尚未判断", "uncertain"),
    ],
)
def test_shared_scope_guards_still_protect_rule_assertions(
    text: str, reason: str
) -> None:
    row = outcome(preview(), text)
    assert row["outcome"] == "needs_review" and row["reason_code"] == reason


@pytest.mark.parametrize(
    "label",
    ["u12-does-not-exist", "伤官见官类似名称", "正印格", "u12-pattern-seal-c20"],
)
def test_unknown_or_similar_identifier_is_not_inferred(label: str) -> None:
    row = outcome(preview(), f"规则[{label}]条件命中")
    assert row["outcome"] == "not_checked" and row["reason_code"] == "u12_rule_unknown"


@pytest.mark.parametrize("system", ["ziwei", "astro"])
def test_bazi_rules_do_not_leak_from_other_system_documents(system: str) -> None:
    row = outcome(preview(system), f"规则[{FALSE_ID}]条件命中")
    assert row["outcome"] == "not_checked" and row["reason_code"] == "u12_rule_unknown"


@pytest.mark.parametrize("value", [0, 1, None, "false", [], {}])
def test_rehashed_non_boolean_met_is_deferred_without_bool_int_equality(value) -> None:
    chart = preview()
    row = next(
        row for row in native(chart)["rule_assessments"] if row["rule_id"] == FALSE_ID
    )
    row["met"] = value
    rehash(chart)
    found = outcome(chart, f"规则[{FALSE_ID}]条件未命中")
    assert (
        found["reason_code"] == "u12_met_not_boolean"
        and found["outcome"] == "needs_review"
    )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("duplicate_id", "u12_identity_ambiguous"),
        ("duplicate_name", "u12_identity_ambiguous"),
        ("false_hit", "u12_false_has_hit"),
        ("true_missing_hit", "u12_hit_assessment_mismatch"),
        ("true_changed_hit", "u12_hit_assessment_mismatch"),
        ("missing_details", "u12_assessment_incomplete"),
        ("unknown_condition", "u12_assessment_incomplete"),
        ("bad_evidence_path", "u12_evidence_paths_invalid"),
    ],
)
def test_assessment_identity_and_true_false_carriers_must_agree(
    mutation: str, reason: str
) -> None:
    chart = preview()
    data = native(chart)
    key = TRUE_ID if mutation.startswith("true_") else FALSE_ID
    row = next(row for row in data["rule_assessments"] if row["rule_id"] == key)
    if mutation == "duplicate_id":
        data["rule_assessments"].append(deepcopy(row))
    elif mutation == "duplicate_name":
        next(item for item in data["rule_assessments"] if item["rule_id"] != key)[
            "name"
        ] = row["name"]
    elif mutation == "false_hit":
        data["rule_hits"].append(deepcopy(row))
    elif mutation == "true_missing_hit":
        data["rule_hits"] = []
        chart["aliases"]["r"] = []
        chart["view"]["rules"] = []
        chart["aliases"]["c"] = [
            alias
            for alias in chart["aliases"]["c"]
            if "/p8/rule_hits/" not in alias["ref"]["path"]
        ]
    elif mutation == "true_changed_hit":
        row["details"]["carrier_test_difference"] = True
    elif mutation == "missing_details":
        row.pop("details")
    elif mutation == "unknown_condition":
        row["condition_ref"] = "unimplemented"
    else:
        row["evidence_paths"] = ["/data/path_that_is_missing"]
    rehash(chart)
    found = outcome(chart, f"规则[{key}]条件命中")
    assert found["reason_code"] == reason and found["outcome"] == "needs_review"


@pytest.mark.parametrize("rows", [None, {}, [], [None]])
def test_missing_or_bad_assessment_container_is_explicitly_deferred(rows) -> None:
    chart = preview()
    native(chart)["rule_assessments"] = rows
    rehash(chart)
    found = outcome(chart, f"规则[{FALSE_ID}]条件未命中")
    assert found["reason_code"] == "u12_assessment_incomplete"


@pytest.mark.parametrize(
    "citation,reason",
    [
        ("〔c99999〕", "citation_missing"),
        ("〔r99999〕", "citation_missing"),
        ("〔r1〕", "citation_not_supporting_field"),
        ("〔c1〕", "citation_not_supporting_field"),
        ("〔c01〕", "citation_syntax_invalid"),
        ("〔r0〕", "citation_syntax_invalid"),
    ],
)
def test_false_condition_cannot_borrow_an_unrelated_rule_alias(
    citation: str, reason: str
) -> None:
    row = outcome(preview(), f"规则[{FALSE_ID}]条件命中" + citation)
    assert row["outcome"] == "needs_review" and row["reason_code"] == reason


def test_false_condition_keeps_actual_c_without_a_traditional_r() -> None:
    chart = preview()
    name = root_alias(chart)
    result = check_u12_rule_assertions(f"规则[{FALSE_ID}]条件未命中〔{name}〕", chart)
    row = result["data"]["checks"][0]
    assert row["outcome"] == "matched" and row["input_c_aliases"]
    selected = [
        alias
        for alias in chart["aliases"]["c"]
        if alias["alias"] in row["input_c_aliases"]
    ]
    assessment = row["assessments"][0]["ref"]
    assert all(
        assessment["document_id"] == alias["ref"]["document_id"]
        and assessment["path"].startswith(alias["ref"]["path"] + "/")
        for alias in selected
    )
    assert row["input_r_aliases"] == result["data"]["input_aliases"]["r"] == []
    assert result["aliases"]["r"][0]["rule_id"].startswith("p8.u12_assertions.")
    assert result["aliases"]["r"][0]["rule_id"] != FALSE_ID


def test_true_condition_reuses_only_the_exact_native_hit_and_its_real_c_evidence() -> (
    None
):
    chart = preview()
    alias = next(row for row in chart["aliases"]["r"] if row.get("rule_id") == TRUE_ID)
    row = outcome(chart, f"规则[{TRUE_ID}]条件命中〔{alias['alias']}〕")
    assert row["outcome"] == "matched" and row["input_r_aliases"] == [alias["alias"]]
    assert set(alias["evidence_aliases"]) <= set(row["input_c_aliases"])
    other = next(
        row
        for row in chart["aliases"]["r"]
        if row.get("rule_id") in TRUE_IDS - {TRUE_ID}
    )
    assert (
        outcome(chart, f"规则[{TRUE_ID}]条件命中〔{other['alias']}〕")["reason_code"]
        == "citation_not_supporting_field"
    )


def test_missing_covering_c_keeps_even_true_assessment_unchecked() -> None:
    chart = preview()
    target = chart["view"]["primary"][0]
    index = next(
        index
        for index, row in enumerate(native(chart)["rule_assessments"])
        if row["rule_id"] == TRUE_ID
    )
    path = target["path"] + f"/p8/rule_assessments/{index}"
    chart["aliases"]["c"] = [
        row
        for row in chart["aliases"]["c"]
        if row["ref"]["document_id"] != target["document_id"]
        or not (row["ref"]["path"] == path or path.startswith(row["ref"]["path"] + "/"))
    ]
    row = outcome(chart, f"规则[{TRUE_ID}]条件命中")
    assert (
        row["outcome"] == "not_checked"
        and row["reason_code"] == "field_evidence_missing"
    )


def test_expected_scope_reuses_type_strict_owner_revision_boundary() -> None:
    chart = preview()
    for key, value in (
        ("owner_user_id", "foreign"),
        ("subject_id", "foreign"),
        ("revision", True),
        ("operation_id", "old"),
    ):
        scope = dict(chart["scope"], **{key: value})
        with pytest.raises(ValueError, match="consistency_scope_mismatch"):
            check_u12_rule_assertions(
                f"规则[{TRUE_ID}]条件命中", chart, expected_scope=scope
            )


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("unknown_id", "u12_rule_unregistered"),
        ("known_other_condition", "u12_registry_metadata_mismatch"),
        ("renamed", "u12_registry_metadata_mismatch"),
        ("parameters", "u12_registry_metadata_mismatch"),
        ("source", "u12_registry_metadata_mismatch"),
        ("school", "u12_registry_metadata_mismatch"),
    ],
)
def test_rehashed_legal_shapes_cannot_self_register_a_rule_or_change_its_metadata(
    mutation: str, reason: str
) -> None:
    chart = preview()
    row = next(
        row for row in native(chart)["rule_assessments"] if row["rule_id"] == FALSE_ID
    )
    if mutation == "unknown_id":
        row["rule_id"] = "u12-foo"
    elif mutation == "known_other_condition":
        row["condition_ref"] = "wealth_weak"
    elif mutation == "renamed":
        row["name"] = "冒名的伤官见官"
    elif mutation == "parameters":
        row["parameters"] = {"gods": ["正印", "比肩"]}
    elif mutation == "source":
        row["source"] = {"book": "未登记的书", "chapter": "第一章"}
    else:
        row["school"] = "通用"
    rehash(chart)
    found = outcome(chart, f"规则[{row['rule_id']}]条件未命中")
    assert found["outcome"] == "needs_review" and found["reason_code"] == reason


@pytest.mark.parametrize(
    "name,prefix,reason",
    [
        ("如果", "如果出生资料完整", "hypothetical"),
        ("对方", "对方出生资料已确认", "other_subject"),
    ],
)
def test_unselected_bad_name_cannot_mask_context_guards_after_rehash(
    name: str, prefix: str, reason: str
) -> None:
    chart = preview()
    row = next(
        row for row in native(chart)["rule_assessments"] if row["rule_id"] == FALSE_ID
    )
    row["name"] = name
    rehash(chart)
    result = check_u12_rule_assertions(
        prefix + "，规则[u12-combo-output-killer]条件命中", chart
    )
    assert result["data"]["status"] == "needs_review"
    assert all(
        item["outcome"] == "needs_review" and item["reason_code"] == reason
        for item in result["data"]["checks"]
    )

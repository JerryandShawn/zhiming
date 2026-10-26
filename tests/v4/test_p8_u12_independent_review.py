"""Independent rehashed-carrier and sentence-scope attacks on the separate U12 API."""

from __future__ import annotations

from copy import deepcopy

import pytest

from mingjing_core.skills.consistency_u12 import check_u12_rule_assertions
from tests.v4.p8_u12_assertions_context import native, preview, rehash

TRUE_ID = "u12-pattern-seal-c2"
FALSE_ID = "u12-combo-hurting-officer-officer"


def _selected(chart: dict, key: str = TRUE_ID) -> dict:
    return next(
        row for row in native(chart)["rule_assessments"] if row["rule_id"] == key
    )


def _sync_hit(chart: dict, row: dict, old_key: str = TRUE_ID) -> None:
    hits = native(chart)["rule_hits"]
    index = next(index for index, hit in enumerate(hits) if hit["rule_id"] == old_key)
    hits[index] = deepcopy(row)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("school", "synthetic-foreign-school", "u12_registry_metadata_mismatch"),
        ("source", {"book": "未登记原典"}, "u12_registry_metadata_mismatch"),
        ("condition_ref", "climate_missing", "u12_registry_metadata_mismatch"),
        ("name", "正印格已经成立", "u12_registry_metadata_mismatch"),
        ("rule_id", "u12-synthetic-injected", "u12_rule_unregistered"),
    ],
)
def test_true_assessment_and_hit_cannot_jointly_self_register_after_full_rehash(
    field: str, value, reason: str
) -> None:
    chart = preview()
    row = _selected(chart)
    row[field] = value
    _sync_hit(chart, row)
    if field == "rule_id":
        for alias in chart["aliases"]["r"]:
            if alias.get("rule_id") == TRUE_ID:
                alias["rule_id"] = value
    rehash(chart)
    result = check_u12_rule_assertions(f"规则[{row['rule_id']}]条件命中", chart)
    found = result["data"]["checks"][0]
    assert found["outcome"] == "needs_review" and found["reason_code"] == reason
    assert not found["input_r_aliases"]


@pytest.mark.parametrize(
    "bad_name,heading,reason",
    [
        ("如果", "如果资料完整，以下是假设资料：", "hypothetical"),
        ("对方", "对方的盘面：", "other_subject"),
        ("北京时间", "北京时间结果：", "comparison_basis"),
        ("你说", "你说的资料：", "quoted_or_reported"),
    ],
)
def test_an_unselected_unknown_row_cannot_erase_a_carried_context_guard(
    bad_name: str, heading: str, reason: str
) -> None:
    chart = preview()
    unselected = _selected(chart, FALSE_ID)
    unselected["name"] = bad_name
    unselected["rule_id"] = "u12-unregistered-context-carrier"
    rehash(chart)
    answer = heading + "\n" + f"规则[{TRUE_ID}]条件命中"
    result = check_u12_rule_assertions(answer, chart)
    assert result["data"]["checks"]
    assert all(
        row["outcome"] == "needs_review" and row["reason_code"] == reason
        for row in result["data"]["checks"]
    )


@pytest.mark.parametrize("scope_revision", [True, 1.0, "1"])
def test_recomputed_alias_claim_does_not_make_a_different_scope_type_equivalent(
    scope_revision,
) -> None:
    chart = preview()
    chart["aliases"]["c"][0]["scope"] = dict(chart["scope"], revision=scope_revision)
    rehash(chart)
    with pytest.raises(ValueError, match="^consistency_chart_invalid$"):
        check_u12_rule_assertions(f"规则[{TRUE_ID}]条件命中", chart)


@pytest.mark.parametrize("scope_revision", [True, 1.0, "1"])
def test_expected_revision_type_stays_strict_even_for_a_supported_true_rule(
    scope_revision,
) -> None:
    chart = preview()
    expected = dict(chart["scope"], revision=scope_revision)
    with pytest.raises(ValueError, match="^consistency_scope_mismatch$"):
        check_u12_rule_assertions(
            f"规则[{TRUE_ID}]条件命中", chart, expected_scope=expected
        )


@pytest.mark.parametrize("met", [1, "true", None])
def test_a_rehashed_true_hit_with_a_non_bool_met_is_rejected_before_comparison(
    met,
) -> None:
    chart = preview()
    row = _selected(chart)
    row["met"] = met
    _sync_hit(chart, row)
    rehash(chart)
    with pytest.raises(ValueError, match="^consistency_chart_invalid$"):
        check_u12_rule_assertions(f"规则[{TRUE_ID}]条件命中", chart)


@pytest.mark.parametrize("field", ["rule_id", "rules_version"])
def test_rehashed_rule_alias_metadata_cannot_borrow_another_registration(
    field: str,
) -> None:
    chart = preview()
    alias = next(row for row in chart["aliases"]["r"] if row.get("rule_id") == TRUE_ID)
    alias[field] = FALSE_ID if field == "rule_id" else "synthetic-foreign-version"
    rehash(chart)
    with pytest.raises(ValueError, match="^consistency_chart_invalid$"):
        check_u12_rule_assertions(f"规则[{TRUE_ID}]条件命中〔{alias['alias']}〕", chart)


@pytest.mark.parametrize(
    "answer,reason",
    [
        (f"“另一人的陈述。规则[{TRUE_ID}]条件命中”", "quoted_or_reported"),
        (f"北京时间结果：\n规则[{TRUE_ID}]条件命中", "comparison_basis"),
        (f"小禾的盘面：\n规则[{TRUE_ID}]条件命中", "other_subject"),
        (f"规则[{TRUE_ID}]条件命中，才怪", "complex_negation"),
    ],
)
def test_true_matching_rule_does_not_override_quotation_or_external_scope(
    answer: str, reason: str
) -> None:
    result = check_u12_rule_assertions(answer, preview())
    assert result["data"]["checks"]
    assert all(
        row["outcome"] == "needs_review" and row["reason_code"] == reason
        for row in result["data"]["checks"]
    )


def test_a_matched_condition_does_not_validate_a_separate_effectiveness_claim() -> None:
    answer = f"规则[{TRUE_ID}]条件命中，格局已经成格。"
    result = check_u12_rule_assertions(answer, preview())
    rows = result["data"]["checks"]
    assert [row["outcome"] for row in rows] == ["matched", "needs_review"]
    assert rows[1]["reason_code"] == "u12_effectiveness_not_evaluated"
    assert result["data"]["status"] == "needs_review"

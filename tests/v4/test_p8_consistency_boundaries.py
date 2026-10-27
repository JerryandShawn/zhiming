"""Alias namespaces, stale scopes and candidate ambiguity remain explicit boundaries."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import claim_id, document_id
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.consistency import check_chart_consistency

ROOT = Path(__file__).resolve().parents[2]


def preview(system: str = "bazi") -> dict:
    return json.loads(
        (ROOT / f"docs/v4/contracts/samples/ayuan_{system}.json").read_text(
            encoding="utf8"
        )
    )


def rehash(source: dict) -> None:
    mapping = {}
    for row in source["documents"]:
        old = row["document_id"]
        row["document_id"] = document_id(
            source["scope"], row["kind"], row["source_sha256"], row["payload"]
        )
        mapping[old] = row["document_id"]
    for references in source["view"].values():
        for ref in references:
            ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
    for ref in source.get("boundary_alerts", []):
        ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
    documents = {row["document_id"]: row["payload"] for row in source["documents"]}
    for rows in source["aliases"].values():
        for row in rows:
            row["ref"]["document_id"] = mapping.get(
                row["ref"]["document_id"], row["ref"]["document_id"]
            )
            row["value_sha256"] = content_hash(
                pointer(documents[row["ref"]["document_id"]], row["ref"]["path"])
            )
            row["claim_id"] = claim_id(row)


def primary(source: dict) -> tuple[dict, dict]:
    ref = source["view"]["primary"][0]
    doc = next(
        row for row in source["documents"] if row["document_id"] == ref["document_id"]
    )
    return doc, pointer(doc["payload"], ref["path"])


def root_alias(source: dict) -> str:
    ref = source["view"]["primary"][0]
    return next(row["alias"] for row in source["aliases"]["c"] if row["ref"] == ref)


@pytest.mark.parametrize("value", [None, False, True, 4, 1.5, [], {}, "x" * 32001])
def test_invalid_answer_type_or_resource_bound_raises_without_private_text(
    value,
) -> None:
    with pytest.raises(ValueError, match="^consistency_answer_invalid$"):
        check_chart_consistency(value, preview())


@pytest.mark.parametrize(
    "field,value",
    [
        ("owner_user_id", "foreign-owner"),
        ("subject_id", "foreign-subject"),
        ("revision", 2),
        ("operation_id", "previous-operation"),
        ("revision", True),
    ],
)
def test_expected_context_checks_owner_subject_revision_operation_and_type(
    field, value
) -> None:
    chart = preview()
    expected = dict(chart["scope"], **{field: value})
    with pytest.raises(ValueError, match="^consistency_scope_mismatch$"):
        check_chart_consistency("日主是丁", chart, expected_scope=expected)


@pytest.mark.parametrize(
    "expected", [{}, {"owner_user_id": "someone"}, [], "owner", False]
)
def test_expected_scope_must_be_a_complete_context_not_a_partial_owner_hint(
    expected,
) -> None:
    with pytest.raises(ValueError, match="^consistency_scope_mismatch$"):
        check_chart_consistency("日主是丁", preview(), expected_scope=expected)


@pytest.mark.parametrize(
    "mutation", ["document", "claim", "branch", "primary", "scope", "version"]
)
def test_invalid_handoff_is_rejected_before_parsing_an_answer(mutation: str) -> None:
    chart = preview()
    if mutation == "document":
        primary(chart)[1]["pillars"]["day"]["gan"] = "甲"
    elif mutation == "claim":
        chart["aliases"]["c"][0]["claim_id"] = "demo-claim-" + "0" * 64
    elif mutation == "branch":
        row = chart["aliases"]["c"][0]
        row["branch_id"] = "foreign"
        row["claim_id"] = claim_id(row)
    elif mutation == "primary":
        chart["view"]["primary"] = [deepcopy(chart["view"]["diagnostics"][0])]
    elif mutation == "scope":
        chart["scope"]["subject_id"] = "foreign"
    else:
        chart["contract_version"] = "future-unreviewed-version"
    with pytest.raises(ValueError, match="^consistency_chart_invalid$"):
        check_chart_consistency("日主是丁", chart)


@pytest.mark.parametrize(
    "citation",
    ["〔c0〕", "〔c01〕", "〔r0〕", "〔c-1〕", "〔C1〕", "〔x1〕", "〔c１〕"],
)
def test_malformed_alias_is_deferred_instead_of_silently_removed(citation: str) -> None:
    row = check_chart_consistency("日主是甲" + citation, preview())["data"]["checks"][0]
    assert (
        row["outcome"] == "needs_review"
        and row["reason_code"] == "citation_syntax_invalid"
    )


@pytest.mark.parametrize(
    "citation,reason",
    [
        ("〔c999999〕", "citation_missing"),
        ("〔r999999〕", "citation_missing"),
        ("〔c1〕", "citation_not_supporting_field"),
        ("〔r1〕", "citation_not_supporting_field"),
    ],
)
def test_missing_or_unrelated_current_alias_does_not_authenticate_a_day_master(
    citation: str, reason: str
) -> None:
    row = check_chart_consistency("日主是甲" + citation, preview())["data"]["checks"][0]
    assert row["outcome"] == "needs_review" and row["reason_code"] == reason


def test_actual_covering_alias_can_be_used_without_new_input_alias_registration() -> (
    None
):
    chart = preview()
    name = root_alias(chart)
    result = check_chart_consistency(
        f"日主〔{name}〕是丁〔{name}〕", chart, expected_scope=chart["scope"]
    )
    row = result["data"]["checks"][0]
    assert row["outcome"] == "matched" and row["input_c_aliases"] == [name]
    assert row["input_citations"] == "〔" + name + "〕"
    assert result["data"]["input_aliases"]["c"][0] in chart["aliases"]["c"]
    assert result["aliases"]["r"][0]["rule_id"].startswith("p8.consistency.")


def test_candidate_methods_disagree_without_a_false_unique_useful_value() -> None:
    chart = preview()
    primary(chart)[1]["p8"]["useful_candidates"]["balancing"][1]["candidate_stems"] = [
        "甲"
    ]
    rehash(chart)
    result = check_chart_consistency("扶抑候选天干包括甲", chart)
    assert result["data"]["checks"][0]["reason_code"] == "multiple_methods_or_branches"
    explicit = check_chart_consistency(
        "扶抑[p8-month-root-exposed-v1]候选天干包括甲", chart
    )
    assert explicit["data"]["status"] == "inconsistent"


def test_unspecified_pattern_useful_path_does_not_union_two_different_candidates() -> (
    None
):
    result = check_chart_consistency("格局候选天干包括壬", preview())
    assert result["data"]["status"] == "needs_review"
    assert result["data"]["checks"][0]["reason_code"] == "multiple_methods_or_branches"


def test_missing_day_stem_does_not_fall_back_to_unverified_ten_god_or_text_guess() -> (
    None
):
    chart = preview()
    primary(chart)[1]["pillars"]["day"].pop("gan")
    rehash(chart)
    assert check_chart_consistency("日主是丁", chart)["data"]["status"] == "not_checked"


def test_a_fact_without_a_covering_input_alias_is_not_reported_as_verified() -> None:
    chart = preview()
    name = root_alias(chart)
    assert all(name not in row["evidence_aliases"] for row in chart["aliases"]["r"])
    chart["aliases"]["c"] = [
        row for row in chart["aliases"]["c"] if row["alias"] != name
    ]
    assert check_chart_consistency("日主是丁", chart)["data"]["status"] == "not_checked"


def test_two_actual_primary_branches_with_different_stems_require_review() -> None:
    chart = preview()
    doc, _ = primary(chart)
    index = int(chart["view"]["primary"][0]["path"].split("/")[2])
    branch = deepcopy(doc["payload"]["charts"][index])
    branch["id"] += "-second-candidate"
    branch["time_basis"]["instant_id"] += "-second-candidate"
    branch["data"]["pillars"]["day"]["gan"] = "甲"
    doc["payload"]["charts"].append(branch)
    ref = {
        "document_id": doc["document_id"],
        "path": f"/charts/{len(doc['payload']['charts']) - 1}/data",
    }
    chart["view"]["primary"].append(ref)
    alias = deepcopy(
        next(row for row in chart["aliases"]["c"] if row["alias"] == root_alias(chart))
    )
    alias.update(alias="c9998", ref=ref, branch_id=branch["id"])
    chart["aliases"]["c"].append(alias)
    rehash(chart)
    result = check_chart_consistency("日主是甲", chart)
    assert result["data"]["checks"][0]["reason_code"] == "multiple_methods_or_branches"
    assert result["data"]["status"] == "needs_review"


@pytest.mark.parametrize(
    "text", ["命宫主星有天相", "本命太阳在双鱼座", "本命火星在第12宫"]
)
def test_field_from_another_system_is_not_inferred_from_a_bazi_document(
    text: str,
) -> None:
    result = check_chart_consistency(text, preview())
    assert result["data"]["status"] == "not_checked"
    assert result["data"]["checks"][0]["reason_code"] == "field_unavailable"

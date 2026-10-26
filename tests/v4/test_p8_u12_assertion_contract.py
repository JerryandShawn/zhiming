"""A new API/schema keeps old readers honest and retains real native provenance."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from p8_u12_assertions_context import ROOT, TRUE_IDS, preview

from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.consistency import check_chart_consistency
from mingjing_core.skills.consistency_u12 import check_u12_rule_assertions

ANSWER = (
    "规则[u12-combo-hurting-officer-officer]条件命中。"
    "规则[u12-pattern-seal-c2]条件命中。"
    "规则[u12-combo-output-killer]条件未命中。完整夺食成立。"
)


def output() -> dict:
    return check_u12_rule_assertions(ANSWER, preview())


def test_independent_contract_validates_new_output_and_old_reader_rejects_new_field_version() -> (
    None
):
    current = json.loads(
        (ROOT / "docs/v4/contracts/u12_rule_assertions.schema.json").read_text(
            encoding="utf8"
        )
    )
    original = json.loads(
        (ROOT / "docs/v4/contracts/chart_consistency.schema.json").read_text(
            encoding="utf8"
        )
    )
    Draft202012Validator.check_schema(current)
    Draft202012Validator(current).validate(output())
    assert list(Draft202012Validator(original).iter_errors(output()))
    unchanged = check_chart_consistency("日主是丁", preview())
    Draft202012Validator(original).validate(unchanged)
    assert unchanged["version"] == "p8-chart-consistency-preview-v1"


def test_own_aliases_bind_real_results_and_do_not_turn_a_false_native_rule_into_a_hit() -> (
    None
):
    result = output()
    root = {
        key: result[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    assert result["document_id"] == "tool-" + content_hash(root)
    c_rows = {row["alias"]: row for row in result["aliases"]["c"]}
    for rows in result["aliases"].values():
        for row in rows:
            value = pointer(result, row["path"])
            assert row["value_sha256"] == content_hash(value)
            assert row["claim_id"] == "claim-" + content_hash(
                [result["document_id"], row["path"], content_hash(value)]
            )
            if row["alias"].startswith("r"):
                assert value["met"] is True and row["rule_id"] == value["rule_id"]
                assert row["rule_id"].startswith("p8.u12_assertions.")
                assert all(name in c_rows for name in row["evidence_aliases"])
    assert result["data"]["checks"][0]["expected_values"] == [False]
    assert result["data"]["checks"][0]["input_r_aliases"] == []
    assert len(result["data"]["checks"][1]["input_r_aliases"]) == 1


def test_actual_met_refs_static_source_scope_and_underlying_paths_resolve_in_original() -> (
    None
):
    chart = preview()
    docs = {row["document_id"]: row["payload"] for row in chart["documents"]}
    aliases = {row["alias"]: row for rows in chart["aliases"].values() for row in rows}
    result = output()
    for check in result["data"]["checks"]:
        for index, ref in enumerate(check["source_refs"]):
            assert (
                pointer(docs[ref["document_id"]], ref["path"])
                is check["expected_values"][index]
            )
        for ref in check.get("evidence_refs", []):
            pointer(docs[ref["document_id"]], ref["path"])
        for row in check.get("assessments", []):
            native = pointer(docs[row["ref"]["document_id"]], row["ref"]["path"])
            assert native["rule_id"] == row["rule_id"] and native["met"] is row["met"]
            assert row["condition_scope"] == native["details"]["scope"]
            assert row["notes"] == native["notes"]
            assert bool(check["input_r_aliases"]) is (row["rule_id"] in TRUE_IDS)
        for name in check["input_c_aliases"] + check["input_r_aliases"]:
            assert aliases[name] in result["data"]["input_aliases"][name[0]]


def test_schema_rejects_missing_assessment_metadata_on_a_claimed_checked_result() -> (
    None
):
    schema = json.loads(
        (ROOT / "docs/v4/contracts/u12_rule_assertions.schema.json").read_text(
            encoding="utf8"
        )
    )
    invalid = deepcopy(output())
    invalid["data"]["checks"][0].pop("assessments")
    assert list(Draft202012Validator(schema).iter_errors(invalid))


def test_committed_synthetic_sample_matches_current_result_without_rewriting_old_samples() -> (
    None
):
    sample = json.loads(
        (ROOT / "docs/v4/contracts/samples/u12-assertions-ayuan.json").read_text(
            encoding="utf8"
        )
    )
    assert sample["fixture_kind"] == "synthetic_u12_condition_assertion_preview"
    assert sample["answer_text"] == ANSWER and sample["result"] == output()


@pytest.mark.parametrize(
    "text,status",
    [
        ("", "not_checked"),
        ("日主是甲", "not_checked"),
        ("如果你这是伤官见官", "needs_review"),
        ("你这是伤官见官", "inconsistent"),
        ("你不是伤官见官", "no_contradiction_found"),
    ],
)
def test_new_api_covers_only_recognized_u12_statements_and_never_echoes_answer(
    text: str, status: str
) -> None:
    result = check_u12_rule_assertions(text, preview())
    assert result["data"]["status"] == status
    assert sum(result["data"]["coverage"].values()) == len(result["data"]["checks"])
    assert result["effects"]["model_calls"] == result["effects"]["writes"] == 0

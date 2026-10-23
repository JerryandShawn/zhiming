"""The checker has content-bound own aliases and retains native input references."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.consistency import check_chart_consistency

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs/v4/contracts"
EXAMPLES = {
    "bazi": "日主是甲。正印格候选筛选通过。调候候选天干包括甲。用神已定为庚。",
    "ziwei": "命宫主星包括天相。夫妻宫主星包括天府。田宅宫是空宫。",
    "astro": "本命太阳在双鱼21.2度。本命木星在第8宫。行运太阳在白羊座。",
}


def preview(system: str) -> dict:
    return json.loads(
        (CONTRACTS / f"samples/ayuan_{system}.json").read_text(encoding="utf8")
    )


@pytest.mark.parametrize("system,text", EXAMPLES.items())
def test_all_system_outputs_match_self_contained_schema_and_real_input_references(
    system: str, text: str
) -> None:
    chart = preview(system)
    result = check_chart_consistency(text, chart, expected_scope=chart["scope"])
    schema = json.loads(
        (CONTRACTS / "chart_consistency.schema.json").read_text(encoding="utf8")
    )
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)
    raw = {row["document_id"]: row["payload"] for row in chart["documents"]}
    names = {row["alias"]: row for rows in chart["aliases"].values() for row in rows}
    assert result["scope"] == chart["scope"]
    assert result["data"]["policy"] == "record_only"
    if system == "bazi":
        source = result["data"]["checks"][0]["fact_sources"][0]["source"]
        assert source["path"].endswith("time_basis_candidates.py")
        assert source["engine_versions"]["lunar-python"]
        assert source["declared_method"]["day_boundary"] == "23:00_advances_day"
        assert (
            pointer(
                raw[source["method_ref"]["document_id"]], source["method_ref"]["path"]
            )
            == source["declared_method"]
        )
    for row in result["data"]["checks"]:
        assert 0 <= row["span"]["start"] < row["span"]["end"] <= len(text)
        for ref in row["source_refs"]:
            assert pointer(raw[ref["document_id"]], ref["path"]) is not None
        for name in row["input_c_aliases"] + row["input_r_aliases"]:
            assert names[name] in result["data"]["input_aliases"][name[0]]
        assert all(
            item["source"] is not None and item["school"]
            for item in row["fact_sources"]
        )


@pytest.mark.parametrize("system,text", EXAMPLES.items())
def test_ephemeral_c_r_aliases_bind_actual_result_values_and_named_checker_rules(
    system: str, text: str
) -> None:
    result = check_chart_consistency(text, preview(system))
    root = {
        key: result[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    assert result["document_id"] == "tool-" + content_hash(root)
    c_names = {row["alias"] for row in result["aliases"]["c"]}
    for rows in result["aliases"].values():
        for alias in rows:
            value = pointer(result, alias["path"])
            digest = content_hash(value)
            assert alias["value_sha256"] == digest
            assert alias["claim_id"] == "claim-" + content_hash(
                [result["document_id"], alias["path"], digest]
            )
            if alias["alias"].startswith("r"):
                assert value["met"] is True and value["rule_id"] == alias["rule_id"]
                assert set(alias["evidence_aliases"]) <= c_names
                assert value["school"] == "project-explicit-text-grammar-v1"
                assert "不是命理" in value["meaning"]


@pytest.mark.parametrize(
    "text", ["", "日主是丁", "如果日主是甲", "日主是甲", "工作准备"]
)
def test_coverage_counts_only_recognized_clauses_not_unseen_natural_language(
    text: str,
) -> None:
    result = check_chart_consistency(text, preview("bazi"))
    rows = result["data"]["checks"]
    assert sum(result["data"]["coverage"].values()) == len(rows)
    assert result["data"]["coverage"]["checked"] == sum(
        row["outcome"] in ("matched", "contradiction") for row in rows
    )
    assert len(result["rule_hits"]) == len(rows)


@pytest.mark.parametrize("system", list(EXAMPLES))
def test_committed_synthetic_examples_equal_current_pure_result(system: str) -> None:
    path = CONTRACTS / f"samples/consistency-ayuan-{system}.json"
    example = json.loads(path.read_text(encoding="utf8"))
    assert example["fixture_kind"] == "synthetic_assertion_preview"
    assert example["result"] == check_chart_consistency(
        example["answer_text"], preview(system)
    )
    assert example["result"]["data"]["status"] == "inconsistent"


def test_schema_rejects_an_unreviewed_outcome_and_nonzero_effect() -> None:
    schema = json.loads(
        (CONTRACTS / "chart_consistency.schema.json").read_text(encoding="utf8")
    )
    value = check_chart_consistency("日主是丁", preview("bazi"))
    invalid = deepcopy(value)
    invalid["data"]["checks"][0]["outcome"] = "definitely_correct"
    assert list(Draft202012Validator(schema).iter_errors(invalid))
    invalid = deepcopy(value)
    invalid["effects"]["model_calls"] = 1
    assert list(Draft202012Validator(schema).iter_errors(invalid))

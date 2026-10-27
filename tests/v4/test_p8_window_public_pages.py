"""Public frontend fixtures preserve ranking and page-local evidence meaning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer

ROOT = Path(__file__).resolve().parents[2] / "docs/v4/contracts"
SAMPLES = ROOT / "samples"
NAMES = (
    "window-search-ayuan-contract-20261021-27.json",
    "window-search-ayuan-page2.json",
    "window-search-ayuan-empty.json",
)


def _sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf8"))


@pytest.mark.parametrize("name", NAMES)
def test_real_public_page_has_schema_and_content_bound_local_aliases(name: str) -> None:
    value = _sample(name)
    schema = json.loads((ROOT / "window_search.schema.json").read_text("utf8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    core = {
        key: value[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    assert value["document_id"] == "tool-" + content_hash(core)
    cs = {row["alias"]: row for row in value["aliases"]["c"]}
    for row in value["aliases"]["c"] + value["aliases"]["r"]:
        assert row["value_sha256"] == content_hash(pointer(value, row["path"]))
    for row in value["aliases"]["r"]:
        hit = pointer(value, row["path"])
        assert hit["met"] is True and hit["rule_id"] == row["rule_id"]
        assert [cs[name]["path"] for name in row["evidence_aliases"]] == hit[
            "evidence_paths"
        ]


def test_full_page_second_page_and_empty_page_share_exact_query_and_ranking() -> None:
    full, second, empty = map(_sample, NAMES)
    assert full["scope"] == second["scope"] == empty["scope"]
    assert full["data"]["trace"] == second["data"]["trace"] == empty["data"]["trace"]
    assert full["data"]["ranking_summary"] == second["data"]["ranking_summary"]
    assert full["data"]["ranking_summary"] == empty["data"]["ranking_summary"]
    fields = ("date", "rank", "score")
    expected = [
        tuple(row[key] for key in fields) for row in full["data"]["candidates"][3:6]
    ]
    assert [
        tuple(row[key] for key in fields) for row in second["data"]["candidates"]
    ] == expected
    assert second["data"]["pagination"] == {
        "total": 7,
        "offset": 3,
        "limit": 3,
        "returned": 3,
        "has_more": True,
        "next_offset": 6,
    }
    assert (
        empty["data"]["candidates"]
        == empty["data"]["observations"]
        == empty["rule_hits"]
        == []
    )
    assert empty["aliases"] == {"c": [], "r": []}
    assert empty["data"]["pagination"] == {
        "total": 7,
        "offset": 7,
        "limit": 3,
        "returned": 0,
        "has_more": False,
        "next_offset": None,
    }


def test_second_page_scoring_links_reference_this_page_and_preserve_sums() -> None:
    value = _sample(NAMES[1])
    for row in value["data"]["candidates"]:
        contributions = []
        for group in ("positive_hits", "negative_hits", "neutral_hits"):
            for link in row[group]:
                hit = value["rule_hits"][link["rule_hit_index"]]
                assert hit["contribution"] == link["contribution"]
                contributions.append(link["contribution"])
        assert row["score"] == sum(contributions)

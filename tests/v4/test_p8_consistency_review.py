"""Independent false-positive review: withdrawn claims, context and native types."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.benchmarks.handoff_refs import claim_id, document_id
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.skills.consistency import check_chart_consistency

ROOT = Path(__file__).resolve().parents[2]


def _chart(system: str = "bazi") -> dict:
    path = ROOT / f"docs/v4/contracts/samples/ayuan_{system}.json"
    return json.loads(path.read_text(encoding="utf8"))


def _rehash(source: dict) -> None:
    mapping = {}
    for row in source["documents"]:
        old = row["document_id"]
        row["document_id"] = document_id(
            source["scope"], row["kind"], row["source_sha256"], row["payload"]
        )
        mapping[old] = row["document_id"]
    references = [ref for refs in source["view"].values() for ref in refs]
    references.extend(source.get("boundary_alerts", []))
    for ref in references:
        ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
    documents = {row["document_id"]: row["payload"] for row in source["documents"]}
    for rows in source["aliases"].values():
        for row in rows:
            ref = row["ref"]
            ref["document_id"] = mapping.get(ref["document_id"], ref["document_id"])
            row["value_sha256"] = content_hash(
                pointer(documents[ref["document_id"]], ref["path"])
            )
            row["claim_id"] = claim_id(row)


def _assert_deferred(answer: str, chart: dict) -> dict:
    result = check_chart_consistency(answer, chart)
    data = result["data"]
    assert data["status"] in ("needs_review", "not_checked")
    assert data["coverage"]["checked"] == 0
    assert not any(row["outcome"] == "contradiction" for row in data["checks"])
    return result


@pytest.mark.parametrize(
    "answer",
    [
        "日主是甲，这个说法不成立。",
        "日主不是丁，这种说法不对。",
        "日主是甲，才怪。",
        "日主是丁，这个说法不成立。",
    ],
)
def test_withdrawn_or_denied_assertion_is_not_compared_as_an_affirmation(
    answer: str,
) -> None:
    _assert_deferred(answer, _chart())


@pytest.mark.parametrize(
    "answer",
    [
        "这是小禾的命盘。日主是甲。",
        "朋友的命盘：\n日主是甲。",
        "北京时间的盘面：\n日主是甲。",
        "下面是钟表时结果。\n日主是甲。",
        "引用的说法如下。\n日主是甲。",
        "旧盘结果。\n日主是甲。",
    ],
)
def test_an_unqualified_claim_in_a_context_block_keeps_its_context(answer: str) -> None:
    _assert_deferred(answer, _chart())


def test_a_primary_basis_claim_without_context_guards_still_finds_real_conflict() -> (
    None
):
    result = check_chart_consistency("你的日主是甲。", _chart())
    assert result["data"]["status"] == "inconsistent"
    assert result["data"]["checks"][0]["expected_values"] == ["丁"]


@pytest.mark.parametrize(
    ("field", "value", "answer"),
    [
        ("house", True, "本命太阳在第1宫"),
        ("retrograde", 0, "本命太阳顺行"),
        ("longitude", True, "本命太阳在双鱼1度"),
    ],
)
def test_rehashed_malformed_native_types_cannot_become_a_matching_fact(
    field: str, value, answer: str
) -> None:
    chart = _chart("astro")
    ref = chart["view"]["primary"][0]
    doc = next(
        row for row in chart["documents"] if row["document_id"] == ref["document_id"]
    )
    pointer(doc["payload"], ref["path"])["planets"]["太阳"][field] = value
    _rehash(chart)
    try:
        result = check_chart_consistency(answer, chart)
    except ValueError as error:
        assert str(error).startswith("consistency_")
    else:
        assert result["data"]["status"] in ("needs_review", "not_checked")
        assert result["data"]["coverage"]["checked"] == 0


@pytest.mark.parametrize("revision", [1.0, "1"])
def test_expected_revision_is_not_coerced_from_float_or_string(revision) -> None:
    chart = _chart()
    expected = {**chart["scope"], "revision": revision}
    with pytest.raises(ValueError, match="^consistency_scope_mismatch$"):
        check_chart_consistency("日主是丁", chart, expected_scope=expected)


def test_expected_scope_rejects_an_extra_session_key() -> None:
    chart = _chart()
    expected = {**chart["scope"], "session_id": "synthetic-other-session"}
    with pytest.raises(ValueError, match="^consistency_scope_mismatch$"):
        check_chart_consistency("日主是丁", chart, expected_scope=expected)


def test_recomputed_hashes_do_not_claim_provider_or_authorization_validation() -> None:
    chart = _chart()
    before = deepcopy(chart)
    for document in chart["documents"]:
        document["source_sha256"] = {"synthetic-untrusted-provider": "0" * 64}
    _rehash(chart)
    result = check_chart_consistency("日主是丁", chart, expected_scope=chart["scope"])
    assert chart["documents"][0]["document_id"] != before["documents"][0]["document_id"]
    assert result["data"]["status"] == "no_contradiction_found"
    limits = " ".join(result["limits"])
    assert "不是签名" in limits and "provider" in limits and "撤销" in limits
    assert result["data"]["policy"] == "record_only"


def test_input_and_comparison_aliases_resolve_in_their_separate_namespaces() -> None:
    chart = _chart()
    result = check_chart_consistency("日主是丁", chart)
    inputs = result["data"]["input_aliases"]
    assert inputs["c"]
    for row in inputs["c"]:
        assert row in chart["aliases"]["c"]
    for row in result["aliases"]["c"] + result["aliases"]["r"]:
        assert row["value_sha256"] == content_hash(pointer(result, row["path"]))
    assert all(
        row["rule_id"].startswith("p8.consistency.") for row in result["rule_hits"]
    )
    assert all("不是命理格局" in row["meaning"] for row in result["rule_hits"])

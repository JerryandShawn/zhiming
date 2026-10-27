"""Offline morning content from seven real-computed synthetic snapshots."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.adapters.charts.tool_evidence import evidence_result, pointer
from mingjing_core.skills.morning_content import morning_content

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "docs/v4/contracts/samples/daily_transit"


def sample(day: int = 21) -> dict:
    return json.loads((SAMPLES / f"ayuan_2026-10-{day}.json").read_bytes())


def render(value: dict, **kwargs: object) -> dict:
    arguments = {"expected_scope": value["scope"], "target_date": value["data"]["date"]}
    return morning_content(value, **(arguments | kwargs))


@pytest.mark.parametrize("day", range(21, 28))
def test_seven_computed_days_have_real_resolvable_cards(day: int) -> None:
    source = sample(day)
    before = deepcopy(source)
    result = render(source)
    committed = (
        ROOT / "docs/v4/contracts/samples/morning_content" / f"ayuan_2026-10-{day}.json"
    )
    assert result == json.loads(committed.read_bytes())
    assert result == render(source)
    assert source == before
    assert {point["system"] for point in result["points"]} == {"bazi", "ziwei", "astro"}
    for point in result["points"]:
        assert point["school"] and point["source"]
        for category in ("c", "r"):
            for name in point[category + "_aliases"]:
                row = next(
                    row for row in result["aliases"][category] if row["alias"] == name
                )
                assert pointer(source, row["path"]) is not None
                assert "〔" + name + "〕" in point["text"]
        if point["system"] in ("bazi", "ziwei"):
            row = next(
                row
                for row in source["aliases"]["r"]
                if row["alias"] == point["r_aliases"][0]
            )
            assert pointer(source, row["path"])["context"]["layer"] == "daily"
    assert "正午" in result["limits"][0]
    assert result["effects"] == {"model_calls": 0, "writes": 0, "sends": 0}
    assert all(
        word not in json.dumps(result, ensure_ascii=False) for word in ("保证", "一定")
    )


@pytest.mark.parametrize(
    "field", ["owner_user_id", "subject_id", "revision", "operation_id"]
)
def test_scope_mismatch_rejected(field: str) -> None:
    value = sample()
    changed = value["scope"] | {field: "wrong"}
    with pytest.raises(ValueError, match="morning_content_input_invalid"):
        render(value, expected_scope=changed)


@pytest.mark.parametrize(
    "mutation", ["data", "false_hit", "alias", "hash", "source", "date"]
)
def test_tampered_evidence_rejected(mutation: str) -> None:
    value = sample()
    if mutation == "data":
        value["data"]["bazi"]["natal_pillars"]["day"] = "甲子"
    elif mutation == "false_hit":
        value["rule_hits"][0]["met"] = False
    elif mutation == "alias":
        value["aliases"]["r"][0]["evidence_aliases"] = ["c999"]
    elif mutation == "hash":
        value["document_id"] = "tool-fake"
    elif mutation == "source":
        value["rule_hits"][0]["source"] = {}
    else:
        value["data"]["date"] = "2026-10-22"
    with pytest.raises(ValueError, match="morning_content_input_invalid"):
        render(value)


def test_wrong_target_day_and_non_iso_day_rejected() -> None:
    for day in ("2026-10-22", "20261021", "private-birth-text"):
        with pytest.raises(ValueError, match="^morning_content_input_invalid$"):
            render(sample(), target_date=day)


def test_no_hits_does_not_invent_good_or_bad_day() -> None:
    value = sample()
    root = evidence_result(
        value["version"], value["data"], [], value["sources"], value["scope"]
    )
    result = render(root)
    assert result["status"] == "insufficient_evidence"
    assert result["points"] == result["rule_hits"] == []
    assert result["aliases"] == {"c": [], "r": []}


def test_output_has_no_birth_or_full_chart_copy() -> None:
    result = render(sample())
    text = json.dumps(result, ensure_ascii=False)
    assert "1994-03-12" not in text
    assert "natal_planets" not in result
    assert "data" not in result


@pytest.mark.parametrize(
    "context", [None, [], {}, {"system": "astro", "kind": "unknown"}]
)
def test_malformed_context_raises_safe_code(context: object) -> None:
    value = sample()
    hit = deepcopy(value["rule_hits"][-1])
    hit["context"] = context
    rebuilt = evidence_result(
        value["version"], value["data"], [hit], value["sources"], value["scope"]
    )
    with pytest.raises(ValueError, match="morning_content_context_invalid"):
        render(rebuilt)

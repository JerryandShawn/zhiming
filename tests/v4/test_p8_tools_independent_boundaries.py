"""Additional typed-carrier, atomic preflight and published-source edge review."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from mingjing_core.adapters.charts import daily_transit_natal as natal_module
from mingjing_core.adapters.charts.p8_adapter import P8ChartAdapter
from mingjing_core.adapters.charts.synastry import synastry
from mingjing_core.adapters.charts.tool_evidence import content_hash, pointer
from mingjing_core.adapters.charts.window_search import _score_results

CONTRACTS = Path(__file__).resolve().parents[2] / "docs/v4/contracts"
SAMPLES = CONTRACTS / "samples"
DAY = "2026-10-21"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf8"))


def _daily() -> dict:
    return _json(SAMPLES / f"daily_transit/ayuan_{DAY}.json")


def _rehash_daily(value: dict) -> None:
    core = {
        key: value[key] for key in ("version", "scope", "data", "rule_hits", "sources")
    }
    value["document_id"] = "tool-" + content_hash(core)


@pytest.mark.parametrize("revision", [True, 1.0], ids=["boolean", "equal-float"])
def test_rehashed_daily_scope_does_not_substitute_equal_but_different_types(
    revision,
) -> None:
    daily = _daily()
    expected = deepcopy(daily["scope"])
    daily["scope"]["revision"] = revision
    _rehash_daily(daily)
    with pytest.raises(ValueError, match="^window_daily_scope_mismatch$"):
        _score_results(expected, [DAY], "签约", [daily])


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("unknown_iana", "daily_transit_natal_invalid"),
        ("future_birth", "daily_transit_before_birth"),
    ],
)
def test_invalid_second_semantic_input_does_not_prepare_the_first_person(
    mutation: str, reason: str, monkeypatch
) -> None:
    request = _json(SAMPLES / "synastry-ayuan-xiaohe-input.json")
    if mutation == "unknown_iana":
        request["chart_b"]["birth"]["place"]["tz"] = "Mars/Olympus"
    else:
        request["chart_b"]["birth"]["date"] = "2027-01-01"
    calls = []

    def forbidden(natal: dict, day: str):
        calls.append((natal["subject_id"], day))
        raise AssertionError("invalid input reached natal preparation")

    monkeypatch.setattr(natal_module, "prepare_natal", forbidden)
    with pytest.raises(ValueError, match="^" + reason + "$"):
        synastry(**request)
    assert calls == []


@pytest.mark.parametrize(
    "mutation,value",
    [
        ("zero", 0),
        ("string-false", "false"),
        ("missing", None),
        ("promoted_true", True),
        ("fact_zero", 0),
    ],
)
def test_rehashed_completeness_must_match_the_actual_boolean_relationship_fact(
    mutation: str,
    value,
) -> None:
    daily = _daily()
    hit = next(
        row for row in daily["rule_hits"] if row["context"].get("complete") is False
    )
    actual = pointer(daily, hit["evidence_paths"][0])
    assert actual["complete"] is False
    if mutation == "missing":
        hit["context"].pop("complete")
    elif mutation == "fact_zero":
        actual["complete"] = value
    else:
        hit["context"]["complete"] = value
    _rehash_daily(daily)
    with pytest.raises(ValueError, match="^window_daily_evidence_invalid$"):
        _score_results(daily["scope"], [DAY], "签约", [daily])


def test_adapter_consent_precedes_nonfinite_payload_checks_and_worker_dispatch(
    monkeypatch,
) -> None:
    request = _json(SAMPLES / "synastry-ayuan-xiaohe-input.json")
    request["consent"] = "pending"
    request["chart_b"]["birth"]["place"]["lon"] = float("nan")
    adapter = P8ChartAdapter(request["chart_a"]["owner_user_id"], python="unused")
    calls = []
    monkeypatch.setattr(adapter, "_request", lambda *args: calls.append(args))
    with pytest.raises(ValueError, match="^CONSENT_REQUIRED"):
        adapter.synastry(request)
    assert calls == []


@pytest.mark.parametrize(
    "tool", ["daily_transit", "window_search", "almanac", "synastry"]
)
def test_success_schemas_reject_targeted_timezone_index_or_scope_type_corruption(
    tool: str,
) -> None:
    filenames = {
        "daily_transit": f"daily_transit/ayuan_{DAY}.json",
        "window_search": "window-search-ayuan-page2.json",
        "almanac": "almanac-20261021.json",
        "synastry": "synastry-ayuan-xiaohe.json",
    }
    validator = Draft202012Validator(
        _json(CONTRACTS / f"{tool}.schema.json"), format_checker=FormatChecker()
    )
    sample = _json(SAMPLES / filenames[tool])
    validator.validate(sample)
    if tool == "daily_transit":
        sample["data"]["snapshot_at"] = DAY + "T12:00:00+09:00"
    elif tool == "window_search":
        sample["data"]["candidates"][0]["positive_hits"][0]["rule_hit_index"] = True
    elif tool == "almanac":
        sample["data"]["lunar"]["month"] = 0
    else:
        sample["scope"]["revisions"][1] = True
    with pytest.raises(ValidationError):
        validator.validate(sample)


def test_second_page_copies_the_actual_published_daily_hit_and_field_values() -> None:
    page = _json(SAMPLES / "window-search-ayuan-page2.json")
    for observation in page["data"]["observations"]:
        day = observation["date"]
        daily = _json(SAMPLES / f"daily_transit/ayuan_{day}.json")
        assert (
            observation["daily_hit"]
            == daily["rule_hits"][observation["daily_rule_index"]]
        )
        for fact in observation["facts"]:
            expected = pointer(daily, fact["path"])
            assert type(fact["value"]) is type(expected) and fact["value"] == expected
        # Published standalone daily calls use their own operation_id; values are
        # identical, but reconstruct the window scope before comparing its ID.
        daily["scope"] = deepcopy(page["scope"])
        _rehash_daily(daily)
        assert daily["document_id"] == observation["daily_document_id"]

"""Final live-evaluation shortlist is bounded; fake replay proves material only."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from mingjing_core.adapters.charts.benchmarks.final_prep_v7 import (
    CATEGORIES,
    DIRECTORY,
    ROOT,
    FinalScenario,
    load_final_cases,
)
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario
from tools.eval.targets.fake_target import FakeTarget

CASES = load_final_cases()


def evaluate(value: dict) -> dict:
    target = FakeTarget()
    try:
        return evaluate_scenario(FinalScenario.model_validate(value), target)
    finally:
        target.close()


@pytest.mark.parametrize("scenario", CASES, ids=lambda row: row.id)
def test_each_material_replays_with_original_engine(scenario: FinalScenario) -> None:
    result = evaluate(scenario.model_dump())
    assert result["status"] == "passed", result["failed_assertions"]
    assert result["judge_model_calls"] == 0


def test_exact_29_five_safety_and_all_batches_have_selection_rationale() -> None:
    manifest = json.loads((DIRECTORY / "manifest.json").read_bytes())
    assert len(CASES) == manifest["count"] == 29 <= 30
    assert manifest["safety_count"] == 5
    assert {row.id for row in CASES if row.category == "safety"} == {
        "S01",
        "S02",
        "S03",
        "S04",
        "K04",
    }
    assert {row["id"] for row in manifest["cases"]} == set(CATEGORIES)
    assert {row["group"] for row in manifest["cases"]} == {
        "safety",
        "memory",
        "p8",
        "critic",
        "streaming",
        "morning",
        "tarot",
    }
    for row in manifest["cases"]:
        assert all(
            row[key] for key in ("source", "tests", "expected_behavior", "rationale")
        )
        if row["source"] != "19":
            source = (ROOT / row["source_path"]).read_bytes().replace(b"\r\n", b"\n")
            assert hashlib.sha256(source).hexdigest() == row["source_sha256_lf"]
            copy = (DIRECTORY / "scenarios" / (row["id"] + ".yaml")).read_bytes()
            assert copy.replace(b"\r\n", b"\n") == source


@pytest.mark.parametrize(
    "identity", ["K04", "KU03", "J03", "J04", "X08", "PR03", "CR01"]
)
def test_wrong_observation_is_not_completed_from_expect(identity: str) -> None:
    value = next(row for row in CASES if row.id == identity).model_dump(
        exclude_none=True
    )
    actions = value["scripted"][0]["model"]
    if identity in {"PR03", "CR01", "J04"}:
        actions[-1]["text"] = {
            "PR03": "每天来看，记得打卡",
            "CR01": "已经确定成格",
            "J04": "10月21日周四",
        }[identity]
    elif identity == "KU03":
        next(row["receipt"] for row in actions if "receipt" in row)["write_status"] = (
            "saved"
        )
    else:
        db = next(row["db"] for row in actions if "db" in row)
        if identity == "K04":
            db["run_meta"]["delivery_latency_ms"] = 20001
        elif identity == "J03":
            db["review"]["issues"][0]["triggered"] = True
        else:
            db["stream"]["replayed_event_ids"] = ["event-2", "event-2", "event-3"]
    assert evaluate(value)["status"] == "failed"


@pytest.mark.parametrize("field", ["id", "category", "extra", "clock", "turn"])
def test_isolated_namespace_preserves_strict_contract(field: str) -> None:
    value = deepcopy(CASES[0].model_dump())
    if field == "extra":
        value["unexpected"] = True
    elif field == "turn":
        value["scripted"][0]["turn"] = 2
    else:
        value[field] = {
            "id": "S99",
            "category": "time",
            "clock": "2026-10-17T10:30:00",
        }[field]
    with pytest.raises(ValidationError):
        FinalScenario.model_validate(value)
    extension = next(row for row in CASES if row.id == "K04")
    with pytest.raises(ValidationError):
        Scenario.model_validate(extension.model_dump())


@pytest.mark.parametrize(
    "state",
    [{}, {"valid_to": "2026-10-17T10:30:00+08:00", "superseded_by": "new-city"}],
)
def test_undo_requires_observed_restoration_not_missing_or_stale(state: dict) -> None:
    value = next(row for row in CASES if row.id == "KU04").model_dump()
    value["scripted"][0]["model"][0]["db"]["memory_update"]["old"] = state
    assert evaluate(value)["status"] == "failed"


@pytest.mark.parametrize(
    ("key", "bad"),
    [("cited_rule_count", 0), ("unresolved_count", 1), ("missing_used_claim_count", 1)],
)
def test_rule_references_require_actual_resolved_and_used_claims(
    key: str, bad: int
) -> None:
    value = next(row for row in CASES if row.id == "CR01").model_dump()
    check = value["scripted"][0]["model"][2]["db"]["run_meta"]["rule_citation_check"]
    check[key] = bad
    assert evaluate(value)["status"] == "failed"

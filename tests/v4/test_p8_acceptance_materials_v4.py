"""New questions use original scoring and reject corrupt traces, without business claims."""

from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from mingjing_core.adapters.charts.benchmarks.acceptance_scenarios import (
    ROOT,
    SCENARIOS,
    P8Scenario,
    load_p8_scenarios,
)
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.fake_target import FakeTarget

CASES = load_p8_scenarios()


def evaluate(value: P8Scenario) -> dict:
    target = FakeTarget()
    try:
        return evaluate_scenario(value, target)
    finally:
        target.close()


@pytest.mark.parametrize("scenario", CASES, ids=lambda case: case.id)
def test_each_new_case_replays_with_original_assertion_engine(
    scenario: P8Scenario,
) -> None:
    result = evaluate(scenario)
    assert result["status"] == "passed", result["failed_assertions"]
    assert result["judge_model_calls"] == 0
    assert scenario.seed.profile == (
        "empty_profile" if scenario.id == "P8AL02" else "default_synthetic"
    )


@pytest.mark.parametrize("scenario", CASES, ids=lambda case: case.id)
def test_blank_answer_fails_instead_of_being_completed_from_expect(
    scenario: P8Scenario,
) -> None:
    value = scenario.model_dump()
    for action in value["scripted"][0]["model"]:
        if action.get("text") is not None:
            action["text"] = ""
    assert evaluate(P8Scenario.model_validate(value))["status"] == "failed"


@pytest.mark.parametrize(
    "scenario",
    [case for case in CASES if case.turns[0].expect.tools_called],
    ids=lambda case: case.id,
)
def test_missing_expected_tool_fails(scenario: P8Scenario) -> None:
    value = scenario.model_dump(exclude_none=True)
    value["scripted"][0]["model"] = [
        action for action in value["scripted"][0]["model"] if "tool_call" not in action
    ]
    assert evaluate(P8Scenario.model_validate(value))["status"] == "failed"


@pytest.mark.parametrize("identity", ["P8WS03", "P8AL03", "P8SY01", "P8SY03"])
def test_refused_scenarios_catch_computation_and_wrong_rejection(identity: str) -> None:
    scenario = next(case for case in CASES if case.id == identity)
    value = scenario.model_dump(exclude_none=True)
    observation = next(
        action["db"]["p8_acceptance"]
        for action in value["scripted"][0]["model"]
        if "db" in action
    )
    tool = scenario.turns[0].expect.tools_called[0]
    observation["engine_calls"][tool] = 1
    observation["refusal_code"] = "ENGINE_FAILED"
    assert evaluate(P8Scenario.model_validate(value))["status"] == "failed"


@pytest.mark.parametrize("mutation", ["citation", "persistence", "leaked_birth"])
def test_synastry_forbids_fake_aliases_long_term_writes_and_birth_leaks(
    mutation: str,
) -> None:
    identity = "P8SY01" if mutation == "leaked_birth" else "P8SY02"
    scenario = next(case for case in CASES if case.id == identity)
    value = scenario.model_dump(exclude_none=True)
    actions = value["scripted"][0]["model"]
    if mutation == "persistence":
        next(action["db"]["p8_acceptance"] for action in actions if "db" in action)[
            "long_term_writes"
        ] = 1
    else:
        actions[-1]["text"] += (
            "〔tmp1〕" if mutation == "citation" else "1995-08-27 14:10"
        )
    assert evaluate(P8Scenario.model_validate(value))["status"] == "failed"


def test_incognito_cannot_call_a_new_tool() -> None:
    value = next(case for case in CASES if case.id == "P8DT03").model_dump(
        exclude_none=True
    )
    value["scripted"][0]["model"].insert(
        0, {"tool_call": {"name": "daily_transit", "arguments": {}}}
    )
    assert evaluate(P8Scenario.model_validate(value))["status"] == "failed"


@pytest.mark.parametrize(
    "mutation", ["id", "category", "target", "clock", "extra", "script"]
)
def test_new_namespace_does_not_relax_original_shape_contract(mutation: str) -> None:
    value = CASES[0].model_dump(exclude_none=True)
    if mutation == "id":
        value["id"] = "P8DT99"
    elif mutation == "category":
        value["category"] = "time"
    elif mutation == "target":
        value["targets"] = ["v3", "v4"]
    elif mutation == "clock":
        value["clock"] = "2026-10-27T10:30:00"
    elif mutation == "extra":
        value["unexpected"] = True
    else:
        value["scripted"][0]["turn"] = 2
    with pytest.raises(ValidationError):
        P8Scenario.model_validate(value)


def test_legacy_schema_corpus_and_seed_files_are_unchanged() -> None:
    manifest = json.loads(
        (SCENARIOS.parent / "legacy_readonly_manifest.json").read_text(encoding="utf8")
    )
    for name, digest in manifest["files"].items():
        actual = hashlib.sha256(
            (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        assert actual == digest, name
    assert len(load_scenarios()) == 80
    with pytest.raises(ValidationError):
        Scenario.model_validate(CASES[0].model_dump())


def test_count_distribution_and_no_model_submitted_birth_or_consent() -> None:
    assert len(CASES) == 13
    assert {
        prefix: sum(case.id.startswith(prefix) for case in CASES)
        for prefix in ("P8DT", "P8WS", "P8AL", "P8SY", "P8BA")
    } == {"P8DT": 3, "P8WS": 3, "P8AL": 3, "P8SY": 3, "P8BA": 1}
    for case in CASES:
        for step in case.scripted:
            for action in step.model:
                if action.tool_call:
                    assert not {"birth", "chart_a", "chart_b", "consent"}.intersection(
                        action.tool_call.arguments
                    )


def test_selected_numeric_answers_are_bound_to_actual_engine_snapshots() -> None:
    facts = json.loads(
        (SCENARIOS.parent / "golden_facts.json").read_text(encoding="utf8")
    )
    preview = json.loads(
        (ROOT / facts["boundary"]["sample"]).read_text(encoding="utf8")
    )
    payload = next(
        row["payload"]
        for row in preview["documents"]
        if row["document_id"] == facts["boundary"]["document_id"]
    )
    alert = payload["boundary_alerts"][0]
    assert facts["boundary"]["current_pillars"] == alert["current_pillars"]
    assert facts["boundary"]["distance_seconds"] == alert["distance_seconds"]
    assert alert["current_pillars"]["hour"] == "甲辰"
    assert {row["pillars"]["hour"] for row in alert["alternatives"]} == {"甲辰", "癸卯"}
    almanac = json.loads((ROOT / facts["almanac"]["sample"]).read_text(encoding="utf8"))
    assert facts["almanac"]["document_id"] == almanac["document_id"]
    for key, value in facts["almanac"]["fields"].items():
        assert value == almanac["data"][key]

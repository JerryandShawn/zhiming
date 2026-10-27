"""P8 materials reuse scoring and reject corrupt traces; no business gate claim."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

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
DESIGN_DOCUMENT = "docs/v4/07_评测场景集.md"
APPENDIX_SHA256 = "9c21dcb7640a72be7d8c099052752e210a05bee0d2634bf0bd959aaf58159230"


def legacy_body(name: str, raw: bytes) -> bytes:
    raw = raw.replace(b"\r\n", b"\n")
    # PR merge CI includes mainline's reviewed v2.2 appendix (base b9a89b6).
    # Only that exact addition is allowed; original text remains byte-pinned.
    if name == DESIGN_DOCUMENT and "## 附录 B：".encode() in raw:
        start = raw.index("## 附录 B：".encode())
        end = raw.index("## 附录：历法核对数据".encode(), start)
        assert hashlib.sha256(raw[start:end]).hexdigest() == APPENDIX_SHA256
        raw = raw[:start] + raw[end:]
    return raw


def legacy_digest(name: str, raw: bytes) -> str:
    return hashlib.sha256(legacy_body(name, raw)).hexdigest()


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
        actual = legacy_digest(name, (ROOT / name).read_bytes())
        assert actual == digest, name
    assert len(load_scenarios()) == 80
    with pytest.raises(ValidationError):
        Scenario.model_validate(CASES[0].model_dump())


@pytest.mark.parametrize("already_integrated", [False, True])
def test_reviewed_upstream_appendix_does_not_freeze_mainline_design_evolution(
    already_integrated: bool,
) -> None:
    original = legacy_body(DESIGN_DOCUMENT, (ROOT / DESIGN_DOCUMENT).read_bytes())
    appendix = (SCENARIOS.parent / "approved_upstream_appendix_b.md").read_bytes()
    appendix = appendix.replace(b"\r\n", b"\n")
    assert hashlib.sha256(appendix).hexdigest() == APPENDIX_SHA256
    marker = "## 附录：历法核对数据".encode()
    assert original.count(marker) == 1
    integrated = original.replace(marker, appendix + marker, 1)
    assert hashlib.sha256(integrated).hexdigest() == (
        "a637aadca05c412f5b27352769a7ddadc0b75359698b5002a86af30a018e28a6"
    )
    checkout = integrated if already_integrated else original
    assert legacy_body(DESIGN_DOCUMENT, checkout) == original
    assert legacy_digest(DESIGN_DOCUMENT, checkout) == legacy_digest(
        DESIGN_DOCUMENT, original
    )


@pytest.mark.parametrize("mutation", ["original_text", "appendix", "twice", "runtime"])
def test_upstream_exception_cannot_hide_other_changes(mutation: str) -> None:
    original = legacy_body(DESIGN_DOCUMENT, (ROOT / DESIGN_DOCUMENT).read_bytes())
    appendix = (SCENARIOS.parent / "approved_upstream_appendix_b.md").read_bytes()
    appendix = appendix.replace(b"\r\n", b"\n")
    marker = "## 附录：历法核对数据".encode()
    candidate = original.replace(marker, appendix + marker, 1)
    name = DESIGN_DOCUMENT
    if mutation == "appendix":
        candidate = candidate.replace(b"A01", b"A99", 1)
    elif mutation == "twice":
        candidate = candidate.replace(marker, appendix + marker, 1)
    elif mutation == "runtime":
        name = "tools/eval/scenarios/C01.yaml"
    else:
        candidate = candidate.replace(b"C01", b"C99", 1)
    try:
        digest = legacy_digest(name, candidate)
    except AssertionError:
        return
    assert digest != legacy_digest(DESIGN_DOCUMENT, original)


@pytest.mark.parametrize("merge_checkout", [False, True])
def test_appendix_checks_run_against_both_actual_checkout_shapes(
    monkeypatch: pytest.MonkeyPatch,
    merge_checkout: bool,
) -> None:
    document = ROOT / DESIGN_DOCUMENT
    original_read = Path.read_bytes
    body = legacy_body(DESIGN_DOCUMENT, original_read(document))
    appendix = original_read(SCENARIOS.parent / "approved_upstream_appendix_b.md")
    appendix = appendix.replace(b"\r\n", b"\n")
    marker = "## 附录：历法核对数据".encode()
    checkout = body.replace(marker, appendix + marker, 1) if merge_checkout else body

    def read_bytes(path: Path) -> bytes:
        return checkout if path == document else original_read(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    test_legacy_schema_corpus_and_seed_files_are_unchanged()
    for state in (False, True):
        test_reviewed_upstream_appendix_does_not_freeze_mainline_design_evolution(state)
    for mutation in ("original_text", "appendix", "twice", "runtime"):
        test_upstream_exception_cannot_hide_other_changes(mutation)


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

"""Supplied synthetic observations test the checker, never stand in for product evidence."""

import copy
import hashlib

import pytest

from tools.eval_material_v23.loader import MaterialError, load_materials
from tools.eval_material_v23.observe import evaluate_observation

CASES = {case["id"]: case for case in load_materials()}


def observation(case_id: str, values: dict) -> dict:
    case = CASES[case_id]
    kinds = {check["path"]: check["kind"] for check in case["assertions"]}
    return {
        "schema": "offline-observation-v1",
        "case_id": case_id,
        "mode": "supplied_offline",
        "scope": copy.deepcopy(case["scope"]),
        "observed_at": case["clock"],
        "evidence": [
            {
                "path": path,
                "kind": kinds[path],
                "value": value,
                "artifact_id": "synthetic-checker-input",
                "artifact_sha256": hashlib.sha256(b"synthetic-checker-input").hexdigest(),
                "producer": "manual_annotation" if kinds[path] == "manual_review" else "synthetic_test",
            }
            for path, value in values.items()
        ],
    }


def test_positive_numbers_alternatives_and_explicit_negation_use_only_supplied_trace() -> None:
    supplied = observation(
        "DC01", {"tools_called": ["date_calc"], "text": "还有4天，10月21日面试；不是3天，也不是5天。"}
    )
    result = evaluate_observation(CASES["DC01"], supplied)
    assert result.status == "observed_pass"
    assert "not a product acceptance" in result.evidence_scope


@pytest.mark.parametrize("text", ["还有5天，10月21日。", "还有14天，10月21日。", "不是4天，10月21日。"])
def test_forbidden_or_negated_fact_cannot_pass_by_substring(text: str) -> None:
    supplied = observation("DC01", {"tools_called": ["date_calc"], "text": text})
    assert evaluate_observation(CASES["DC01"], supplied).status == "failed"


@pytest.mark.parametrize("value", [None, "", "  "])
def test_none_or_blank_answer_is_unverified_even_with_successful_tool_trace(value: object) -> None:
    supplied = observation("DC01", {"tools_called": ["date_calc"], "text": value})
    assert evaluate_observation(CASES["DC01"], supplied).status == "unverified"


def test_empty_evidence_list_and_missing_manual_review_cannot_pass() -> None:
    assert evaluate_observation(CASES["DC01"], observation("DC01", {})).status == "unverified"
    supplied = observation("DC02", {"tools_called": ["date_calc"], "text": "周岁32，虚岁33。"})
    assert evaluate_observation(CASES["DC02"], supplied).status == "unverified"
    supplied = observation(
        "DC02", {"tools_called": ["date_calc"], "text": "周岁32，虚岁33。", "review.criteria_1": True}
    )
    assert evaluate_observation(CASES["DC02"], supplied).status == "observed_pass"


def test_false_is_valid_observation_and_never_coerced_from_zero() -> None:
    supplied = observation(
        "J05",
        {
            "meta.review.mode": "evidence_only",
            "meta.answer_delivered": True,
            "meta.program_checks_ran": True,
            "meta.critic_model_called": False,
        },
    )
    assert evaluate_observation(CASES["J05"], supplied).status == "observed_pass"
    supplied["evidence"][-1]["value"] = 0
    assert evaluate_observation(CASES["J05"], supplied).status == "failed"


@pytest.mark.parametrize("field", ["owner_id", "subject_id", "thread_id", "run_id"])
def test_case_evidence_scope_is_not_transferable(field: str) -> None:
    supplied = observation("DC01", {})
    supplied["scope"][field] = "FOREIGN_PRIVATE_MARKER"
    with pytest.raises(MaterialError) as caught:
        evaluate_observation(CASES["DC01"], supplied)
    assert "FOREIGN_PRIVATE_MARKER" not in str(caught.value)


@pytest.mark.parametrize("change", ["extra-pass", "naive-clock", "duplicate-path", "unknown-path", "empty-hash"])
def test_unsupported_or_unbound_observations_are_rejected(change: str) -> None:
    supplied = observation("DC01", {"text": "还有4天，10月21日。"})
    if change == "extra-pass":
        supplied["pass"] = True
    elif change == "naive-clock":
        supplied["observed_at"] = "2026-10-17T10:30:00"
    elif change == "duplicate-path":
        supplied["evidence"].append(copy.deepcopy(supplied["evidence"][0]))
    elif change == "unknown-path":
        supplied["evidence"][0]["path"] = "unrelated.private"
    else:
        supplied["evidence"][0]["artifact_sha256"] = ""
    with pytest.raises(MaterialError):
        evaluate_observation(CASES["DC01"], supplied)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object(), {2: "not-json"}])
def test_python_only_or_nonfinite_observations_are_not_json_evidence(value: object) -> None:
    supplied = observation("DC01", {"text": value})
    with pytest.raises(MaterialError):
        evaluate_observation(CASES["DC01"], supplied)


def test_wrong_evidence_kind_is_not_a_database_or_tool_trace() -> None:
    supplied = observation("DC01", {"tools_called": ["date_calc"], "text": "还有4天，10月21日。"})
    supplied["evidence"][0]["kind"] = "text"
    assert evaluate_observation(CASES["DC01"], supplied).status == "unverified"


def test_explicit_empty_tool_trace_is_not_missing_evidence_for_a_no_tool_requirement() -> None:
    supplied = observation("CL04", {"tools_called": [], "text": "今天宜理发。", "review.criteria_1": True})
    assert evaluate_observation(CASES["CL04"], supplied).status == "observed_pass"


def test_blocked_case_never_accepts_fabricated_observation_as_approval() -> None:
    for case_id in ("PR02", "PR06", "J02", "RT10"):
        result = evaluate_observation(CASES[case_id], {"pass": True})
        assert result.status in {"blocked_decision", "blocked_dependency"}


@pytest.mark.parametrize("change", ["unblock", "rewrite-gold", "unknown-case"])
def test_caller_cannot_mutate_material_policy_or_gold_between_loading_and_checking(change: str) -> None:
    case = copy.deepcopy(CASES["PR02"])
    if change == "unblock":
        case.update(availability="ready_for_observation", blocking_reasons=[])
    elif change == "rewrite-gold":
        case["assertions"][0]["expected"] = False
    else:
        case["id"] = "UN01"
    with pytest.raises(MaterialError, match="case_not_bound_to_loaded_material"):
        evaluate_observation(case)

"""Resume real observations while keeping framework and capability scores separate."""

import json
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tools.eval import runner
from tools.eval.outcomes import is_infrastructure_failure
from tools.eval.report import add_comparison, markdown, summarize
from tools.eval.runner import _resume_cases
from tools.eval.schema import load_scenarios
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget


def report_fixture(*, score: float = 0.5) -> dict[str, Any]:
    cases = [
        {
            "id": "T01",
            "category": "time",
            "status": "passed" if score == 1 else "failed",
            "score": score,
            "failed_assertions": [] if score == 1 else ["turn[1].must_include_all[1]"],
        }
    ]
    return {
        "metadata": {
            "date": "2026-10-17",
            "mode": "live",
            "target": "v3",
            "model": "primary-one",
            "status": "complete",
            "rubric_version": "fixed-v1",
            "rubric_sha256": "rubric-digest",
            "judge_model": "critic-fixed",
            "judge_provider": "configured-model-v3",
            "judge_schema_sha256": "schema-digest",
            "config_version": "config-v1",
        },
        "summary": summarize(cases),
        "cases": cases,
    }


@pytest.mark.parametrize("error_key", ["error_code", "judge_error_code", "target_error_code"])
def test_resume_retries_operational_failures_but_retains_completed_results(tmp_path: Path, error_key: str) -> None:
    metadata = {
        "target": "v3",
        "model": "primary-one",
        "mode": "live",
        "rubric_sha256": "rubric",
        "config_sha256": "config",
        "source_sha256": "source",
        "provider_endpoint_sha256": "endpoint",
    }
    cases = [
        {"id": "T01", "status": "failed", error_key: "ModelUnavailable"},
        {
            "id": "T02",
            "status": "failed",
            "failed_assertions": ["turn[1].must_include_all[1]"],
        },
        {"id": "T03", "status": "passed"},
        {"id": "T08", "status": "n/a on v3"},
        {"id": "T09", "status": "running"},
    ]
    path = tmp_path / "2026-10-17-live-v3-primary.json"
    path.write_text(json.dumps({"metadata": metadata, "cases": cases}), encoding="utf-8")
    reusable = _resume_cases(Namespace(resume=True, output=tmp_path), metadata)
    assert set(reusable) == {"T02", "T03", "T08"}


def compare_to(tmp_path: Path, current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "baseline-v3.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    add_comparison(current, path)
    return current["comparison"]


def test_comparison_allows_different_primary_and_target_with_identical_scoring_scope(
    tmp_path: Path,
) -> None:
    current, baseline = report_fixture(score=0.8), report_fixture(score=0.3)
    current["metadata"].update(model="primary-two", target="v4")
    baseline["cases"].append({"id": "F01", "status": "n/a on v3", "score": None})
    result = compare_to(tmp_path, current, baseline)
    assert result == {
        "baseline": "baseline-v3.json",
        "comparable": True,
        "score_delta": 0.5,
    }


@pytest.mark.parametrize(
    ("report_name", "key", "value", "reason"),
    [
        ("current", "mode", "scripted", "current_not_live"),
        ("current", "target", "fake", "current_not_live"),
        ("current", "status", "incomplete", "current_incomplete"),
        ("baseline", "mode", "scripted", "baseline_not_live"),
        ("baseline", "status", "incomplete", "baseline_incomplete"),
        ("current", "rubric_sha256", "changed", "judge_contract_changed"),
        ("current", "rubric_version", "changed", "judge_contract_changed"),
        ("current", "judge_model", "changed", "judge_contract_changed"),
        ("current", "judge_provider", "changed", "judge_contract_changed"),
        ("current", "judge_schema_sha256", "changed", "judge_contract_changed"),
    ],
)
def test_incomparable_runs_explain_why_without_an_improvement_percentage(
    tmp_path: Path, report_name: str, key: str, value: str, reason: str
) -> None:
    current, baseline = report_fixture(score=1), report_fixture(score=0.3)
    selected = current if report_name == "current" else baseline
    selected["metadata"][key] = value
    result = compare_to(tmp_path, current, baseline)
    assert result["comparable"] is False
    assert result["reason"] == reason
    assert "score_delta" not in result
    rendered = markdown(current)
    assert "不可比较" in rendered
    assert "总分变化" not in rendered


def test_partial_scenario_selection_cannot_claim_global_improvement(
    tmp_path: Path,
) -> None:
    current, baseline = report_fixture(score=1), report_fixture(score=0.3)
    other = deepcopy(baseline["cases"][0])
    other["id"] = "T02"
    baseline["cases"].append(other)
    baseline["summary"] = summarize(baseline["cases"])
    result = compare_to(tmp_path, current, baseline)
    assert result["reason"] == "applicable_scenarios_differ"
    assert "score_delta" not in result


@pytest.mark.parametrize("report_name", ["current", "baseline"])
def test_operational_error_prevents_comparison_even_if_status_was_marked_complete(
    tmp_path: Path, report_name: str
) -> None:
    current, baseline = report_fixture(), report_fixture()
    selected = current if report_name == "current" else baseline
    selected["cases"][0]["target_error_code"] = "ModelUnavailable"
    result = compare_to(tmp_path, current, baseline)
    assert result["reason"] == report_name + "_incomplete"
    assert "score_delta" not in result


def test_legacy_baseline_without_fixed_critic_protocol_is_not_assumed_comparable(
    tmp_path: Path,
) -> None:
    current, baseline = report_fixture(), report_fixture()
    del baseline["metadata"]["judge_schema_sha256"]
    result = compare_to(tmp_path, current, baseline)
    assert result["reason"] == "judge_contract_missing"


def test_absent_baseline_records_reason_without_creating_a_baseline(
    tmp_path: Path,
) -> None:
    report = report_fixture()
    path = tmp_path / "baseline-v3.json"
    add_comparison(report, path)
    assert report["comparison"]["reason"] == "baseline_missing"
    assert not path.exists()


@pytest.mark.parametrize(
    ("case", "expected"),
    [
        ({"error_code": "RuntimeError"}, True),
        ({"judge_error_code": "ValueError"}, True),
        ({"target_error_code": "ModelUnavailable", "error_category": "provider"}, True),
        ({"target_error_code": "ModelUnavailable"}, True),
        ({"target_error_code": "InvalidAnswer", "error_category": "business"}, False),
        ({"target_error_code": "BudgetExceeded", "error_category": "business"}, False),
        ({"status": "failed", "failed_assertions": ["turn[1].judge_score"]}, False),
    ],
)
def test_infrastructure_classifier_preserves_business_failures(case: dict[str, Any], expected: bool) -> None:
    assert is_infrastructure_failure(case) is expected


class FailingObservationTarget(FakeTarget):
    def __init__(self, category: str | None) -> None:
        super().__init__()
        self.category = category

    def send(self, turn: dict[str, Any]) -> TurnResult:
        code = "InvalidAnswer" if self.category == "business" else "ModelUnavailable"
        metadata = {"error_category": self.category} if self.category else {}
        return TurnResult(error=code, metadata=metadata)


@pytest.mark.parametrize("category", ["business", "provider", None])
def test_baseline_records_business_zero_but_refuses_unavailable_infrastructure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, category: str | None
) -> None:
    metadata = report_fixture()["metadata"]
    metadata.update(
        status="running", config_sha256="config", source_sha256="source", provider_endpoint_sha256="endpoint"
    )
    monkeypatch.setattr(runner, "_metadata", lambda *_: metadata)
    monkeypatch.setattr(runner, "_target", lambda *_: FailingObservationTarget(category))
    monkeypatch.setattr(runner, "ModelJudge", lambda *_: None)
    config = {"judge": {"model": "critic-fixed", "rubric": "rubric_v1.md"}}
    args = Namespace(mode="live", target="v3", output=tmp_path, scenario=None, resume=False)
    exit_code = runner._run(args, load_scenarios(), config, "primary-one")
    baseline = tmp_path / "baseline-v3.json"
    assert baseline.exists() is (category == "business")
    path = tmp_path / "2026-10-17-live-v3-primary-one.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["metadata"]["status"] == ("complete" if category == "business" else "incomplete")
    assert report["summary"]["score"] == 0
    assert report["summary"]["count"] == 44
    assert exit_code == (0 if category == "business" else 1)
    reusable = _resume_cases(Namespace(resume=True, output=tmp_path), metadata)
    assert len(reusable) == (80 if category == "business" else 36)
    if category == "business":
        failures = [case for case in reusable.values() if case["status"] != "n/a on v3"]
        assert all(case["score"] == 0 and case["target_error_code"] == "InvalidAnswer" for case in failures)


def test_business_error_zero_is_a_valid_baseline_for_comparison(tmp_path: Path) -> None:
    current, baseline = report_fixture(score=1), report_fixture(score=0)
    baseline["cases"][0].update(target_error_code="InvalidAnswer", error_category="business")
    result = compare_to(tmp_path, current, baseline)
    assert result["comparable"] is True
    assert result["score_delta"] == 1

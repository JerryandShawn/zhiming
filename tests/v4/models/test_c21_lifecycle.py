"""No-network c21 lifecycle, source isolation and membership-boundary integration."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.eval import runner_v2
from tools.eval.contract_v2 import migrate, scenario_v21_hash
from tools.eval.contracts import canonical_hash
from tools.eval.engine_v21 import evaluate_scenario
from tools.eval.evidence_v2 import EvidenceJudge, EvidenceModel
from tools.eval.member_budget import MemberBudget
from tools.eval.quota import ProviderStopped, QuotaGuard
from tools.eval.schema import load_scenarios
from tools.eval.source_v21 import execution_digest
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget


def corpus() -> list[Any]:
    return [migrate(case)[0] for case in load_scenarios()]


def report_for(scenarios: list[Any]) -> dict[str, Any]:
    planned = {case.id: scenario_v21_hash(case) for case in scenarios}
    metadata = runner_v2.metadata_for("scripted", runner_v2.configuration("scripted"))
    metadata.update(
        run_id="test-c21",
        status="incomplete",
        execution_sha256=execution_digest(),
        planned_contracts=planned,
        planned_contracts_sha256=canonical_hash(planned),
    )
    return {"metadata": metadata, "cases": [], "batches": [], "c21_batches": []}


def test_twenty_minute_gap_survives_coordinator_and_budget_recreation(tmp_path: Path) -> None:
    clock = FrozenClock(datetime.fromisoformat("2026-10-18T03:00:00+00:00"))
    budget = MemberBudget(tmp_path / "ledger.json", "test-c21", clock)
    scenarios = corpus()
    report = report_for(scenarios)
    runner_v2._batches(scenarios, report, FakeTarget(), None, budget, tmp_path / "reports", 1)
    first_ids = {case["id"] for case in report["cases"]}
    assert len(first_ids) == 10
    reopened = MemberBudget(tmp_path / "ledger.json", "test-c21", clock)
    with pytest.raises(ProviderStopped) as stopped:
        runner_v2._batches(scenarios, report, FakeTarget(), None, reopened, tmp_path / "reports", 1)
    assert stopped.value.reason == "batch_cooldown" and stopped.value.resume_at
    assert {case["id"] for case in report["cases"]} == first_ids
    clock.advance(timedelta(minutes=20))
    runner_v2._batches(scenarios, report, FakeTarget(), None, reopened, tmp_path / "reports", 1)
    assert len(report["cases"]) == 20
    assert reopened.snapshot()["batches_completed"] == 2


def test_unexpected_interrupt_saves_incomplete_state_without_private_error_text(
    tmp_path: Path, monkeypatch: Any
) -> None:
    class Interrupt(FakeTarget):
        closed = False

        def send(self, turn: dict[str, Any]) -> TurnResult:
            raise KeyboardInterrupt("PRIVATE_TEXT_MUST_NOT_LEAK")

        def close(self) -> None:
            self.closed = True

    target = Interrupt()
    monkeypatch.setattr(runner_v2, "_prepare", lambda *args, **kwargs: (None, target))
    with pytest.raises(KeyboardInterrupt):
        runner_v2.run("scripted", tmp_path / "reports")
    text = (tmp_path / "reports/run-state-c21.json").read_text(encoding="utf-8")
    saved = json.loads(text)
    assert target.closed and saved["metadata"]["status"] == "incomplete"
    assert saved["metadata"]["execution_error_code"] == "KeyboardInterrupt"
    assert "PRIVATE_TEXT" not in text
    assert len(saved["metadata"]["pending_scenario_ids"]) == 80


@pytest.mark.parametrize("reason", ["quota_5h", "quota_weekly", "member_window_limit"])
def test_target_stop_subtype_is_preserved_after_old_engine_execution(reason: str) -> None:
    class Stopped(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            return TurnResult(error="ProviderStopped", metadata={"stop_reason": reason})

    scenario = migrate(next(case for case in load_scenarios() if case.id == "T01"))[0]
    case = evaluate_scenario(scenario, Stopped(), target_name="fake")
    assert case["stop_reason"] == reason and case["score"] == 0


def test_judge_stop_subtype_is_preserved() -> None:
    class Judge:
        def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise ProviderStopped("quota_5h", "judge")

    scenario = migrate(next(case for case in load_scenarios() if case.id == "C04"))[0]
    case = evaluate_scenario(scenario, FakeTarget(), target_name="fake", judge=Judge())
    assert case["stop_reason"] == "quota_5h" and case["stop_role"] == "judge"
    assert case["answers_full"]


def test_tracking_guard_budget_binding_and_actual_request_delta(tmp_path: Path, monkeypatch: Any) -> None:
    clock = FrozenClock(datetime.fromisoformat("2026-10-18T03:00:00+00:00"))
    budget = MemberBudget(tmp_path / "ledger.json", "delta", clock)
    observed = EvidenceModel(object())
    target = runner_v2.EvidenceTarget(
        observed=observed, budget=budget, dsn="postgresql://core_test@127.0.0.1:55480/core_test_e1"
    )

    def reset(instance: Any, seed: dict[str, Any]) -> None:
        instance.model = SimpleNamespace(provider=QuotaGuard(object(), "target"))

    def send(instance: Any, turn: dict[str, Any]) -> TurnResult:
        budget.before_provider_request("target")
        budget.before_provider_request("target")
        return TurnResult(model_calls=1)

    monkeypatch.setattr(runner_v2.V3Target, "reset", reset)
    monkeypatch.setattr(runner_v2.V3Target, "send", send)
    target.reset({})
    assert target.model.provider.budget is budget
    budget.before_batch(["T01"])
    result = target.send({"_index": 1})
    assert result.model_calls == 2 and observed.turn_index == 1


def test_live_preflight_rejects_shared_mainline_database(monkeypatch: Any) -> None:
    monkeypatch.setenv("CORE_TEST_DSN", "postgresql://core_test@127.0.0.1:55480/core_test_main")
    with pytest.raises(SystemExit, match="core_test_e1"):
        runner_v2.e1_dsn()
    monkeypatch.setenv("CORE_TEST_DSN", "postgresql://core_test@127.0.0.1:55480/core_test_e1")
    assert "core_test_e1" in runner_v2.e1_dsn()


@pytest.mark.parametrize("failure", ["grade", "schema", "network", "target"])
def test_infrastructure_failure_stops_without_finishing_batch_or_auto_resume(tmp_path: Path, failure: str) -> None:
    class Provider:
        def generate(self, **kwargs: Any) -> dict[str, Any]:
            if failure == "network":
                raise ConnectionError("PRIVATE_BODY_MUST_NOT_LEAK")
            return {
                "output": {}
                if failure == "schema"
                else {"score": "invalid", "verdict": "pass", "issues": [], "reason": "合成结构"}
            }

    class Target(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            if failure == "target":
                return TurnResult(error="TimeoutError", metadata={"error_category": "provider"})
            return super().send(turn)

    scenarios = corpus()[:2]
    report = report_for(scenarios)
    budget = MemberBudget(tmp_path / "ledger.json", "test-c21")
    judge = EvidenceJudge(Provider(), runner_v2.EVAL / "rubric_v21.md")
    target = Target()
    output = tmp_path / "reports"
    runner_v2._batches(scenarios, report, target, judge, budget, output, 1)
    runner_v2._close_publish(target, report, scenarios, output, judge, budget)
    saved_text = (output / "run-state-c21.json").read_text(encoding="utf-8")
    saved = json.loads(saved_text)
    assert saved["metadata"]["status"] == "incomplete"
    assert saved["metadata"]["execution_error_code"] == "InfrastructureFailure"
    assert saved["metadata"]["pending_scenario_ids"] == [case.id for case in scenarios]
    assert saved["metadata"].get("resume_at") is None
    assert len(saved["cases"]) == 1 and saved["c21_batches"][0]["status"] == "incomplete"
    assert budget.snapshot()["batches_completed"] == 0
    assert "PRIVATE_BODY" not in saved_text
    assert runner_v2._result_code("scripted", saved, budget) == 2
    if failure != "target":
        assert saved["cases"][0]["answers_full"] and saved["evidence_full"][0]["grade"]["status"] == "error"
        expected_code = {"grade": "ValueError", "schema": "KeyError", "network": "ConnectionError"}[failure]
        assert saved["cases"][0]["judge_error_code"] == expected_code


def test_observed_capability_failure_can_complete_a_valid_batch(tmp_path: Path) -> None:
    class WrongAnswer(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            result = super().send(turn)
            result.text = "日期是1900年1月1日。"
            return result

    scenario = next(case for case in corpus() if case.id == "T01")
    report = report_for([scenario])
    budget = MemberBudget(tmp_path / "ledger.json", "test-c21")
    runner_v2._batches([scenario], report, WrongAnswer(), None, budget, tmp_path / "reports", 1)
    assert report["metadata"]["status"] == "complete"
    assert report["cases"][0]["status"] == "failed"
    assert budget.snapshot()["batches_completed"] == 1

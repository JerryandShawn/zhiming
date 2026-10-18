"""Reuse execution/accounting while applying only the explicit v2.1 fact matcher."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tools.eval.engine import evaluate_scenario as execute
from tools.eval.facts_v21 import LANGUAGE_KEYS, factual_checks
from tools.eval.judges import check_assertions
from tools.eval.quota import ProviderStopped
from tools.eval.schema import Scenario
from tools.eval.targets.base import TurnResult


class ObservedTarget:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.results: list[TurnResult] = []

    def reset(self, seed: dict[str, Any]) -> None:
        self.results.clear()
        self.target.reset(seed)

    def send(self, turn: dict[str, Any]) -> TurnResult:
        result = self.target.send(turn)
        self.results.append(result)
        return result

    def inspect_db(self) -> dict[str, Any]:
        return self.target.inspect_db()


class ObservedJudge:
    def __init__(self, judge: Any) -> None:
        self.judge = judge
        self.grades: list[float] = []
        self.stop_reason: str | None = None

    def evaluate(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            reviewed = self.judge.evaluate(payload)
        except ProviderStopped as exc:
            self.stop_reason = exc.reason
            raise
        self.grades.append(reviewed["score"])
        return reviewed


def evaluate_scenario(scenario: Scenario, target: Any, *, target_name: str, judge: Any = None) -> dict[str, Any]:
    observed = ObservedTarget(target)
    grading = ObservedJudge(judge) if judge else None
    case = execute(scenario, observed, target_name=target_name, judge=grading)
    if case["status"] == "n/a on v3" or not observed.results:
        return case
    assertions = []
    for index, result in enumerate(observed.results, 1):
        turn = scenario.turns[index - 1]
        expect = turn.expect.model_dump(exclude_unset=True, exclude_none=True)
        structural = {key: value for key, value in expect.items() if key not in LANGUAGE_KEYS}
        checks = check_assertions(structural, result) + factual_checks(
            expect, result.text, identity=scenario.id, clock=turn.at or scenario.clock
        )
        assertions.extend({"turn": index, **asdict(check)} for check in checks)
    prior_errors = [
        name for name in case["failed_assertions"] if name.endswith(("judge_error", "judge_score", "target_exception"))
    ]
    case["assertions"] = assertions
    case["failed_assertions"] = [
        f"turn[{row['turn']}].{row['name']}" for row in assertions if not row["passed"]
    ] + prior_errors
    case["answers_full"] = [result.text for result in observed.results]
    case["receipts_by_turn"] = [result.receipts for result in observed.results]
    for result in observed.results:
        if result.metadata.get("stop_reason"):
            case["stop_reason"] = result.metadata["stop_reason"]
    if grading and grading.stop_reason:
        case["stop_reason"] = grading.stop_reason
    if case.get("stop_reason"):
        case["score"] = 0.0
        return case
    grades = grading.grades if grading else [1.0] * len(observed.results)
    passed = not case["failed_assertions"] and not case.get("judge_error_code") and not case.get("error_code")
    case["score"] = round(sum(grades) / len(grades), 6) * passed if grades else 0.0
    case["status"] = "passed" if passed and case["score"] == 1 else "failed"
    return case

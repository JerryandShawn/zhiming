"""A failed target cannot pass merely because all weak assertions are satisfied."""

from __future__ import annotations

from typing import Any

import pytest

from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario
from tools.eval.targets.base import TurnResult
from tools.eval.targets.fake_target import FakeTarget


class NoJudgeCall:
    def evaluate(self, _: Any) -> Any:
        raise AssertionError("Target errors must not be sent to an external judge")


@pytest.mark.parametrize("judge", [None, NoJudgeCall()])
@pytest.mark.parametrize("error", ["ModelUnavailable", "EvidenceError", "private unsafe error body"])
def test_target_error_is_hard_failure_even_when_every_assertion_passes(judge: Any, error: str) -> None:
    class BrokenTarget(FakeTarget):
        def send(self, turn: dict[str, Any]) -> TurnResult:
            return TurnResult(text="合成正常文本", error=error, metadata={"error_category": "business"})

    scenario = Scenario.model_validate(
        {
            "id": "Q01",
            "title": "弱断言不能掩盖目标故障",
            "category": "question",
            "clock": "2026-10-17T10:30:00+08:00",
            "seed": {"profile": "empty_profile"},
            "turns": [
                {
                    "user": "合成问题",
                    "expect": {"max_questions": 0, "tools_not_called": ["chart_compute"], "must_include_all": ["正常"]},
                }
            ],
            "scripted": [{"turn": 1, "model": [{"text": "合成正常文本"}]}],
        }
    )
    observed = evaluate_scenario(scenario, BrokenTarget(), judge=judge)
    assert all(check["passed"] for check in observed["assertions"] if check["name"] != "target_error")
    assert [check for check in observed["assertions"] if check["name"] == "target_error"] == [
        {"turn": 1, "name": "target_error", "passed": False}
    ]
    assert observed["status"] == "failed" and observed["score"] == 0
    assert observed["failed_assertions"] == ["turn[1].target_error"]
    assert observed["target_error_code"] == ("TargetFailure" if " " in error else error)
    assert "private unsafe error body" not in str(observed)

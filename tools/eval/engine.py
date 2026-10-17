"""Run scenarios and retain only bounded, synthetic report observations."""

import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.judges import ModelJudge, check_assertions
from tools.eval.schema import Scenario
from tools.eval.targets.base import Target, TurnResult


def _case(identity: str, category: str, status: str) -> dict[str, Any]:
    return {
        "id": identity,
        "category": category,
        "status": status,
        "score": None if status == "n/a on v3" else 0.0,
        "assertions": [],
        "failed_assertions": [],
        "previews": [],
        "model_calls": 0,
        "target_model_calls": 0,
        "judge_model_calls": 0,
        "elapsed_seconds": 0.0,
    }


def evaluate_scenario(
    scenario: Scenario,
    target: Target,
    *,
    target_name: str = "fake",
    judge: ModelJudge | None = None,
) -> dict[str, Any]:
    if target_name == "v3" and "v3" not in scenario.targets:
        return _case(scenario.id, scenario.category, "n/a on v3")
    case = _case(scenario.id, scenario.category, "failed")
    previous_clock = get_clock()
    try:
        set_clock(FrozenClock(datetime.fromisoformat(scenario.clock)))
        seed = scenario.seed.model_dump(mode="json")
        seed.update(
            _scenario_id=scenario.id,
            _clock=scenario.clock,
            _scripted=[step.model_dump(exclude_none=True) for step in scenario.scripted],
        )
        target.reset(seed)
        grades = _evaluate_turns(scenario, target, judge, case)
        passed = all(check["passed"] for check in case["assertions"]) and not case.get("judge_error_code")
        case["score"] = round((sum(grades) / len(grades)) * passed, 6)
        case["status"] = "passed" if passed and case["score"] == 1 else "failed"
    except Exception as exc:
        case["failed_assertions"].append("target_exception")
        case["error_code"] = type(exc).__name__
    finally:
        set_clock(previous_clock)
    case["elapsed_seconds"] = round(case["elapsed_seconds"], 3)
    return case


def _evaluate_turns(scenario: Scenario, target: Target, judge: ModelJudge | None, case: dict[str, Any]) -> list[float]:
    grades: list[float] = []
    for index, turn in enumerate(scenario.turns, 1):
        if turn.at:
            set_clock(FrozenClock(datetime.fromisoformat(turn.at)))
        payload = turn.model_dump(mode="json", exclude={"expect"}, exclude_none=True)
        result = target.send({**payload, "_index": index})
        result.db = target.inspect_db()
        expect = turn.expect.model_dump(exclude_unset=True, exclude_none=True)
        checks = check_assertions(expect, result)
        case["assertions"].extend({"turn": index, **asdict(check)} for check in checks)
        case["failed_assertions"].extend(f"turn[{index}].{check.name}" for check in checks if not check.passed)
        case["model_calls"] += result.model_calls
        case["target_model_calls"] += result.model_calls
        case["elapsed_seconds"] += result.elapsed_seconds
        if result.error:
            safe_code = result.error if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", result.error) else "TargetFailure"
            case["target_error_code"] = safe_code
            category = result.metadata.get("error_category", "unclassified")
            case["error_category"] = category if category in {"provider", "business"} else "unclassified"
        if scenario.seed.synthetic and result.text:
            case["previews"].append(result.text[:200])
        grades.append(_grade(scenario, index, result, judge, case))
    return grades


def _grade(
    scenario: Scenario,
    index: int,
    result: TurnResult,
    judge: ModelJudge | None,
    case: dict[str, Any],
) -> float:
    if judge is None:
        return 1.0
    if result.error:
        return 0.0
    turn = scenario.turns[index - 1]
    reviewed = judge.evaluate(
        {
            "scenario_id": scenario.id,
            "user": turn.user,
            "clock": turn.at or scenario.clock,
            "seed": scenario.seed.model_dump(mode="json"),
            "receipts": result.receipts,
            "tools_called": result.tools_called,
            "criterion": turn.expect.judge,
            "answer": result.text,
        }
    )
    case["model_calls"] += reviewed["model_calls"]
    case["judge_model_calls"] += reviewed["model_calls"]
    case["elapsed_seconds"] += reviewed["elapsed_seconds"]
    if reviewed["error"]:
        case["failed_assertions"].append(f"turn[{index}].judge_error")
        case["judge_error_code"] = reviewed["error"]
    elif reviewed["score"] < 1:
        case["failed_assertions"].append(f"turn[{index}].judge_score")
    return reviewed["score"]

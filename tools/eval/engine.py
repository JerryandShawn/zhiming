"""Run scenarios and retain only bounded, synthetic report observations."""

import re
from dataclasses import asdict
from datetime import datetime
from typing import Any

from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.judges import ModelJudge, check_assertions
from tools.eval.quota import ProviderStopped, guard_judge
from tools.eval.schema import Scenario
from tools.eval.targets.base import Target, TurnResult
from tools.manual_grant import scoped_scenario


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
        "target_model_elapsed_seconds": 0.0,
        "judge_model_elapsed_seconds": 0.0,
        "elapsed_seconds": 0.0,
    }


@scoped_scenario
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
    case["business_clock"] = scenario.clock
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
        if case["status"] != "incomplete":
            case["score"] = round((sum(grades) / len(grades)) * passed, 6)
            case["status"] = "passed" if passed and case["score"] == 1 else "failed"
    except ProviderStopped as exc:
        _record_stop(case, exc.reason, exc.role, exc.provider_http_status, exc.resume_at)
        case["model_calls"] += exc.model_calls
        case[exc.role + "_model_calls"] += exc.model_calls
        case["elapsed_seconds"] += exc.elapsed_seconds
        case[exc.role + "_model_elapsed_seconds"] += exc.elapsed_seconds
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
        case["target_model_elapsed_seconds"] += result.metadata.get("model_elapsed_seconds", result.elapsed_seconds)
        case["elapsed_seconds"] += result.elapsed_seconds
        if result.error:
            safe_code = result.error if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", result.error) else "TargetFailure"
            case["target_error_code"] = safe_code
            category = result.metadata.get("error_category", "unclassified")
            case["error_category"] = category if category in {"provider", "business"} else "unclassified"
        if result.metadata.get("stop_reason"):
            _record_stop(
                case,
                result.metadata["stop_reason"],
                "target",
                result.metadata.get("provider_http_status"),
                result.metadata.get("resume_at"),
            )
        if scenario.seed.synthetic and result.text:
            case["previews"].append(result.text[:200])
        if case["status"] == "incomplete":
            break
        grade = _grade(scenario, index, result, judge, case)
        if judge is not None:
            case.setdefault("private_evidence", []).append(
                {
                    "turn": index,
                    "answer": result.text,
                    "criterion": turn.expect.judge,
                    "score": grade,
                    "judge": case.pop("_private_judge", None),
                }
            )
        grades.append(grade)
        if case.get("stop_reason"):
            break
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
    payload = {
        "scenario_id": scenario.id,
        "user": turn.user,
        "clock": turn.at or scenario.clock,
        "seed": scenario.seed.model_dump(mode="json"),
        "receipts": result.receipts,
        "tools_called": result.tools_called,
        "criterion": turn.expect.judge,
        "answer": result.text,
    }
    guard = guard_judge(judge)
    calls_before = guard.calls if guard else 0
    elapsed_before = guard.elapsed_seconds if guard else 0.0
    try:
        reviewed = judge.evaluate(payload)
    except ProviderStopped as exc:
        _record_stop(case, exc.reason, "judge", exc.provider_http_status, exc.resume_at)
        reviewed = {
            "score": 0.0,
            "model_calls": guard.calls - calls_before if guard else exc.model_calls,
            "elapsed_seconds": guard.elapsed_seconds - elapsed_before if guard else exc.elapsed_seconds,
            "error": "ProviderStopped",
        }
    case["_private_judge"] = {
        "details": reviewed.get("private_reasoning"),
        "error": reviewed.get("error"),
        "reason_missing": not bool(reviewed.get("private_reasoning")),
    }
    physical_calls = guard.calls - calls_before if guard else reviewed["model_calls"]
    case["model_calls"] += physical_calls
    case["judge_model_calls"] += physical_calls
    case["judge_model_elapsed_seconds"] += (
        guard.elapsed_seconds - elapsed_before if guard else reviewed["elapsed_seconds"]
    )
    case["elapsed_seconds"] += reviewed["elapsed_seconds"]
    if reviewed["error"]:
        case["failed_assertions"].append(f"turn[{index}].judge_error")
        case["judge_error_code"] = reviewed["error"]
    elif reviewed["score"] < 1:
        case["failed_assertions"].append(f"turn[{index}].judge_score")
    return reviewed["score"]


def _record_stop(
    case: dict[str, Any],
    reason: str,
    role: str,
    provider_http_status: int | None = None,
    resume_at: str | None = None,
) -> None:
    safe = ProviderStopped(reason, role, provider_http_status=provider_http_status, resume_at=resume_at)
    from mingjing_core.models.quota_mode import current_delegated_session
    from mingjing_core.models.quota_r16 import K31CoreApproval

    session = current_delegated_session()
    if session is not None and isinstance(session.approval, K31CoreApproval):
        from mingjing_core.timekit.clock import SystemClock

        case.update(
            status="incomplete",
            score=None,
            retry_policy="fresh_question_new_run_new_deadline",
            stopped_at=SystemClock().now().isoformat(),
        )
    eligible = safe.reason == "quota_5h" and safe.resume_at is not None
    case.update(
        stop_reason=safe.reason,
        stop_role=safe.role,
        requires_user_decision=not eligible,
        automatic_resume_eligible=eligible,
        permanent_stop=safe.reason == "access_terminated",
    )
    if safe.resume_at is not None:
        case["resume_at"] = safe.resume_at
    if type(provider_http_status) is int and 100 <= provider_http_status <= 599:
        case["provider_http_status"] = provider_http_status

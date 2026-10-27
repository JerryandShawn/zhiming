"""Score only the actual saved turn using native JudgeJournal, never the scenario reset engine."""

from __future__ import annotations

from dataclasses import asdict

from tools.eval.engine import _case
from tools.eval.judge_journal import JudgeJournal
from tools.eval.judges import check_assertions
from tools.eval.judge_context import judge_payload
from tools.eval.quota_resume_evidence import require


def grade_current(target, control, binding, guard, judge, scenario, state):
    index = state["turn"]
    require(type(index) is int and 1 <= index <= len(scenario.turns) and scenario.seed.synthetic is True)
    result = target.completed_result(control, binding, guard)
    result.db = target.inspect_db()
    turn = scenario.turns[index - 1]
    checks = check_assertions(turn.expect.model_dump(exclude_unset=True, exclude_none=True), result)
    reviewed = JudgeJournal(target, control, binding, guard).evaluate(judge)
    packet = judge_payload(scenario, index, result)
    case = _case(scenario.id, scenario.category, "incomplete")
    case["assertions"] = [{"turn": index, **asdict(check)} for check in checks]
    case["failed_assertions"] = [f"turn[{index}].{check.name}" for check in checks if not check.passed]
    score = reviewed["score"] if all(check.passed for check in checks) and not reviewed["error"] else 0.0
    case.update(
        private_evidence=[
            {
                "turn": index,
                "answer": result.text,
                "criterion": turn.expect.judge,
                "score": score,
                "judge_score": reviewed["score"],
                "judge": reviewed.get("private_reasoning"),
                "reason_missing": not bool(reviewed.get("private_reasoning")),
                "tool_effects": result.metadata.get("tool_effects", {}),
                "packet": {key: packet[key] for key in ("packet_sha256", "packet_chars", "truncation")},
            }
        ],
        observed_turn=index,
        current_turn_score=score,
        current_turn_completed=True,
        business_clock=turn.at or scenario.clock,
        previews=[result.text[:200]] if result.text else [],
        scenario_complete=len(scenario.turns) == 1 and index == 1,
        judge_metadata=reviewed.get("judge_metadata", {}),
    )
    if reviewed["error"]:
        case["judge_error_code"] = reviewed["error"]
        case["failed_assertions"].append(f"turn[{index}].judge_error")
    elif reviewed["score"] < 1:
        case["failed_assertions"].append(f"turn[{index}].judge_score")
    if case["scenario_complete"]:
        case.update(
            score=score,
            status="passed" if score == 1 and not case["failed_assertions"] else "failed",
        )
    if reviewed.get("judge_unavailable"):
        case.update(status="judge_unavailable", score=None, current_turn_score=None, judge_unavailable=True)
    from tools.eval.brain_review import mark_brain_review

    mark_brain_review(case)
    return case

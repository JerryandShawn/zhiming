"""Board39 native schedule policy, actual card observations and resolved judge fixtures."""

import pytest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge, check_assertions
from tools.eval.judge_context import judge_payload
from tools.eval.schema import load_scenario
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_target import V4Target
from tools.eval.targets.base import TurnResult


@pytest.mark.parametrize(
    "time,expected",
    [
        ("09:00:00", "2026-10-21T20:00:00+08:00"),
        ("18:30:00", "2026-10-21T18:30:00+08:00"),
        ("22:59:00", "2026-10-21T22:59:00+08:00"),
        ("23:30:00", "2026-10-22T08:30:00+08:00"),
    ],
)
def test_native_followup_evening_and_quiet_hour(time, expected):
    case = execution_overlay(load_scenario("tools/eval/scenarios/M01.yaml"))
    for action in case.scripted[0].model:
        if action.tool_call and action.tool_call.name == "schedule_followup":
            action.tool_call.arguments["due_at"] = "2026-10-21T" + time + "+08:00"
    target = V4Target()
    try:
        result = evaluate_scenario(case, target, target_name="v4")
        assert not result.get("error_code")
        rows = target.repo.list(target.owner, "followup")
        assert len(rows) == 1
        assert datetime.fromisoformat(rows[0]["due_at"]) == datetime.fromisoformat(expected)
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert run["status"] == "succeeded"
    finally:
        target.close()


@pytest.mark.parametrize("ident", ["D01", "Q03", "Q04"])
def test_actual_card_fields_are_private_evidence(ident):
    case = next(c for c in load_core30() if c.id == ident)
    target = V4Target()

    def generate(**kwargs):
        return {
            "output": {
                "score": 1,
                "verdict": "pass",
                "issues": [],
                "reason": "synthetic",
                "deductions": [],
                "expected_clauses": [],
            }
        }

    judge = ModelJudge("synthetic", Path("tools/eval/rubric_v1.md"), SimpleNamespace(generate=generate))
    try:
        result = evaluate_scenario(case, target, target_name="v4", judge=judge)
        assert result["status"] == "passed", result["failed_assertions"]
        effects = result["private_evidence"][0]["tool_effects"]
        if ident == "D01":
            assert len(effects["present_options"]) == 1
        elif ident == "Q03":
            assert effects["ask_user"]
        else:
            assert effects["ask_user"] == []
    finally:
        target.close()


def test_judge_resolves_seed_profile_and_does_not_add_golden_answer():
    case = next(c for c in load_core30() if c.id == "T10")
    result = TurnResult(text="synthetic", metadata={"prior_turns": [{"receipts": [{"write_status": "deleted"}]}]})
    payload = judge_payload(case, 1, result)
    assert payload["resolved_profile"]["name"] == "阿远"
    assert payload["resolved_profile"]["occupation"] == "软件工程师"
    assert "考虑跳槽" in payload["resolved_profile"]["goals"]
    assert payload["resolved_profile"]["birth"]
    assert payload["prior_turns"][0]["receipts"][0]["write_status"] == "deleted"
    assert "scripted" not in payload and "gold" not in payload


def test_birth_card_alternative_requires_actual_fields():
    case = next(c for c in load_core30() if c.id == "C02")
    expect = case.turns[0].expect.model_dump(exclude_none=True)
    result = TurnResult(text="确认资料", tools_called=["profile_update_request"])
    assert not next(c for c in check_assertions(expect, result) if c.name == "profile_confirmation_or_text").passed
    result.metadata = {
        "tool_effects": {
            "profile_requests": [{"status": "pending", "fields": ["birth.date", "birth.time", "birth.city"]}]
        }
    }
    assert next(c for c in check_assertions(expect, result) if c.name == "profile_confirmation_or_text").passed


def test_date_only_today_is_normalized_before_past_time_rejection():
    case = execution_overlay(load_scenario("tools/eval/scenarios/M01.yaml"))
    case.clock = "2026-10-21T10:30:00+08:00"
    case.turns[0].user = "我今天有个面试，挺紧张的"
    for action in case.scripted[0].model:
        if action.tool_call and action.tool_call.name in {"memory_write", "schedule_followup"}:
            action.tool_call.arguments["quote"] = "我今天有个面试"
        if action.tool_call and action.tool_call.name == "schedule_followup":
            action.tool_call.arguments["due_at"] = "2026-10-21T09:00:00+08:00"
    target = V4Target()
    try:
        result = evaluate_scenario(case, target, target_name="v4")
        assert result["status"] == "passed", result["failed_assertions"]
        row = target.repo.list(target.owner, "followup")[0]
        assert datetime.fromisoformat(row["due_at"]) == datetime.fromisoformat("2026-10-21T20:00:00+08:00")
    finally:
        target.close()

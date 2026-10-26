"""An elapsed date-only evening default must not invalidate a future followup."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from mingjing_core.application.agent_tools_followups import schedule_metadata
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenario
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target


@pytest.mark.parametrize(
    "current,proposed,expected",
    [
        ("19:59:59", "2026-10-22T09:00:00+08:00", "2026-10-21T20:00:00+08:00"),
        ("20:00:00", "2026-10-22T09:00:00+08:00", "2026-10-22T09:00:00+08:00"),
        ("22:00:00", "2026-10-22T09:00:00+08:00", "2026-10-22T09:00:00+08:00"),
        ("22:00:00", "2026-10-22T18:30:00+08:00", "2026-10-22T18:30:00+08:00"),
        ("22:00:00", "2026-10-21T21:00:00+08:00", None),
        ("22:00:00", "2026-10-21T09:00:00+08:00", None),
    ],
)
def test_elapsed_evening_keeps_future_original_and_rejects_both_past(current, proposed, expected, p2_repo):
    case = execution_overlay(load_scenario("tools/eval/scenarios/M01.yaml"))
    case.clock = "2026-10-21T" + current + "+08:00"
    case.turns[0].user = "我今天有个面试，挺紧张的"
    for action in case.scripted[0].model:
        if action.tool_call and action.tool_call.name in {"memory_write", "schedule_followup"}:
            action.tool_call.arguments["quote"] = "我今天有个面试"
        if action.tool_call and action.tool_call.name == "schedule_followup":
            action.tool_call.arguments["due_at"] = proposed
    if expected is not None:
        # This in-memory variant has a different clock and proposed time; the
        # frozen M01 YAML stays unchanged, while its DB assertion remains hard.
        for condition in case.turns[0].expect.db:
            if condition.kind == "followup":
                condition.where["data.due_at"] = expected
    target = V4Target()
    try:
        observed = evaluate_scenario(case, target, target_name="v4")
        rows = target.repo.list(target.owner, "followup")
        if expected is None:
            assert rows == []
        else:
            assert observed["status"] == "passed", observed["failed_assertions"]
            assert len(rows) == 1
            assert datetime.fromisoformat(rows[0]["due_at"]) == datetime.fromisoformat(expected)
            run = target.repo.fetch_run(target.owner, target.run_ids[-1])
            assert run["status"] == "succeeded"
            assert rows[0]["event_at"] == "2026-10-21"
    finally:
        target.close()


@pytest.mark.parametrize(
    "event_at,followup,conflict",
    [("2026-10-21", False, True), ("2026-10-21", True, False), ("2026-10-21T12:00:00+08:00", True, True)],
)
def test_next_day_relaxation_applies_only_to_date_only_followups(monkeypatch, event_at, followup, conflict):
    metadata = {"event_at": event_at, "original_expression": "今天"}
    monkeypatch.setattr(
        "mingjing_core.application.agent_tools_followups.event_metadata", lambda *args: (metadata, None)
    )
    result, pending = schedule_metadata(
        SimpleNamespace(timezone=lambda ctx: "Asia/Shanghai"),
        {"quote": "今天的面试"},
        None,
        {},
        datetime.fromisoformat("2026-10-22T09:00:00+08:00"),
        date_only_followup=followup,
    )
    assert result == metadata
    assert (pending is not None) is conflict
    if conflict:
        assert pending["code"] == "date_conflict"

"""R3 recovery uses actual PG journals and native channel-specific delivery."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from psycopg import sql

from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize(("identity", "channel", "outbox_count"), [("X03a", "web", 0), ("X03b", "feishu", 1)])
def test_x03_reclaims_real_crash_without_duplicates_or_manufactured_outbox(
    target: V4Target, identity: str, channel: str, outbox_count: int
) -> None:
    root = Path(__file__).resolve().parents[3]
    scenario = next(case for case in load_scenarios(root / "tools/eval/scenarios_v4") if case.id == identity)
    observed = evaluate_scenario(scenario, target, target_name="v4")
    assert observed["status"] == "passed", observed
    assert "error_code" not in observed and "target_error_code" not in observed, observed
    assert not observed["failed_assertions"]
    assert len(target.run_ids) == 1
    run = target.repo.fetch_run(target.owner, target.run_ids[0])
    assert run["status"] == "succeeded" and run["retry_epoch"] == 0
    rows = target.inspect_db()["entities"]
    assert len([row for row in rows if row["kind"] == "fact"]) == 1
    replies = [row for row in rows if row["kind"] == "message" and row["data"].get("role") == "assistant"]
    assert len(replies) == 1 and replies[0]["data"]["channel"] == channel
    assert len([row for row in rows if row["kind"] == "outbox"]) == outbox_count
    with target.repo.transaction(target.owner) as connection:
        assert (
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(target.repo.table("delivery_outbox"))
            ).fetchone()["n"]
            == outbox_count
        )
    proof = target.case_evidence()
    assert len(proof["tool_steps"]) == 1
    assert [row["name"] for row in proof["semantic_observations"]] == [
        "run.step_committed",
        "run.crashed",
        "run.resumed",
    ] + (["delivery.sent"] if channel == "feishu" else [])
    if channel == "feishu":
        assert target.feishu.proof["sent_count"] == 1
        assert target.feishu.proof["external_channel_sends"] == 0
        target.feishu.finish(run["id"])
        assert len(target.feishu.sent) == 1
        assert len([row for row in target.inspect_db()["entities"] if row["kind"] == "outbox"]) == 1
    else:
        assert target.feishu is None


@pytest.mark.parametrize("stop", ["cancel", "withdraw_source", "wrong_operation"])
@pytest.mark.parametrize("identity", ["X03a", "X03b"])
def test_crashed_evaluation_cannot_reclaim_cancelled_withdrawn_or_other_operation(
    target: V4Target, stop: str, identity: str
) -> None:
    root = Path(__file__).resolve().parents[3]
    case = next(case for case in load_scenarios(root / "tools/eval/scenarios_v4") if case.id == identity)
    seed = case.seed.model_dump(mode="json")
    seed.update(
        _scenario_id=case.id,
        _scripted=[step.model_dump(exclude_none=True) for step in case.scripted],
    )
    clock = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
    try:
        target.reset(seed)
        first = case.turns[0].model_dump(exclude={"expect"}, mode="json")
        target.send(dict(first, _index=1))
        run = target.repo.fetch_run(target.owner, target.run_ids[0])
        second = case.turns[1].model_dump(exclude={"expect"}, mode="json")
        if stop == "cancel":
            DispatcherCancellation(target.repo).request(target.owner, run["id"])
        elif stop == "withdraw_source":
            fact = next(row["data"] for row in target.inspect_db()["entities"] if row["kind"] == "fact")
            target.service.memory.retire_fact(
                target.owner,
                fact["id"],
                expected_revision=fact["revision"],
                scope="source",
            )
        else:
            second["action"]["operation_id"] = "other-operation"
        with pytest.raises(ValueError):
            target.send(dict(second, _index=2))
        after = target.repo.fetch_run(target.owner, run["id"])
        assert after["result"] is None
        assert not [
            row
            for row in target.inspect_db()["entities"]
            if row["kind"] == "message" and row["data"].get("role") == "assistant"
        ]
    finally:
        set_clock(clock)

"""Two real own writes reconcile into one core4 reply without duplicate mutation."""

from __future__ import annotations

from pathlib import Path

import pytest

from mingjing_core.application.agent_commit_versions import persisted_receipts
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def test_consecutive_own_writes_reconcile_versions_receipts_and_idempotent_final(target: V4Target) -> None:
    root = Path(__file__).resolve().parents[3]
    original = next(case for case in load_scenarios(root / "tools/eval/scenarios_v4") if case.id == "M03")
    data = original.model_dump(mode="json")
    data["seed"]["profile"] = "empty_profile"
    data["turns"][0]["user"] = "请记住，我不吃辣，也不喝酒。"
    data["turns"][0]["expect"]["db"][0]["count"] = 2
    data["scripted"][0]["model"] = [
        {
            "tool_call": {
                "name": "memory_write",
                "arguments": {
                    "message_id": "turn-1",
                    "quote": quote,
                    "summary": summary,
                    "kind": "preference",
                },
            }
        }
        for quote, summary in (("我不吃辣", "不吃辣"), ("不喝酒", "不喝酒"))
    ] + [{"text": "已记住这两项饮食偏好。"}]
    observed = evaluate_scenario(Scenario.model_validate(data), target, target_name="v4")
    assert observed["status"] == "passed", observed
    repo, owner, ident = target.repo, target.owner, target.run_ids[0]
    run = repo.fetch_run(owner, ident)
    facts = [row["data"] for row in target.inspect_db()["entities"] if row["kind"] == "fact"]
    assert len(facts) == 2 and len(run["result"]["receipts"]) == 2
    assert len({receipt["_operation"] for receipt in persisted_receipts(repo, run)}) == 2
    assert all("_operation" not in receipt and "operation_id" not in receipt for receipt in run["result"]["receipts"])
    assert all(receipt["write_status"] == "saved" for receipt in run["result"]["receipts"])
    assert all(run["state_version"]["fact:" + fact["id"]] == fact["revision"] for fact in facts)
    assert run["result"]["schema"] == "core4.0" and observed["model_calls"] == 3
    assert target.runtime.execute(target.service, owner, ident, "already-finalized") == run["result"]
    assert repo.fetch_run(owner, ident)["result"] == run["result"] and len(repo.list(owner, "fact")) == 2
    replies = [row for row in repo.list(owner, "message") if row.get("run_id") == ident]
    assert len(replies) == 1 and replies[0]["role"] == "assistant"

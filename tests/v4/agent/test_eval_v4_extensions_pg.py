"""Expanded time, recall and question scripts assert actual persisted outputs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture

CORPUS = Path(__file__).resolve().parents[3] / "tools/eval/scenarios_v4_extensions"


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


@pytest.mark.parametrize(
    "identity", ["T01", "T02", "T08", "R02", "R03", "R07", "Q01", "Q03", "Q06", "S01", "S02", "S03", "X07"]
)
def test_real_pg_t_r_q_extension(identity: str, target: V4Target) -> None:
    case = next(case for case in load_scenarios(CORPUS) if case.id == identity)
    observed = evaluate_scenario(case, target, target_name="v4")
    assert observed["status"] == "passed", observed
    assert observed["target_model_calls"] == 0 if identity == "S03" else observed["target_model_calls"] >= 1
    snapshot = target.inspect_db()
    assert snapshot["run_result"]["schema"] == "core4.0"
    if identity.startswith("T") or identity.startswith("R"):
        assert snapshot["observed_tools"] and snapshot["observed_tools"][0]["status"] == "completed"
    if identity == "X07":
        ingress = snapshot["run_meta"]["ingress"]
        assert ingress["external_channel_sends"] == 0 and ingress["sent_count"] == 1
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        sources = [target.repo.get(target.owner, "message", ident) for ident in run["request"]["source_message_ids"]]
        assert [row["content"] for row in sources] == ["我今天有面试", "有点紧张", "帮我准备一下"]
        assert ingress["source_segments"] == [
            dict(message_id=row["id"], version=row["revision"], start=0, end=len(row["content"])) for row in sources
        ]


def test_changing_time_assertion_cannot_change_real_tool_output(target: V4Target) -> None:
    case = next(case for case in load_scenarios(CORPUS) if case.id == "T02")
    wrong = deepcopy(case.model_dump(mode="json"))
    wrong["turns"][0]["expect"]["db"][0]["equals"] = "WRONG_HOUR_SENTINEL"
    observed = evaluate_scenario(Scenario.model_validate(wrong), target, target_name="v4")
    assert observed["status"] == "failed" and "turn[1].db[1]" in observed["failed_assertions"]
    actual = target.inspect_db()["observed_tools"][0]["output"]["data"]
    assert actual["ganzhi"]["hour"] == "丙子"

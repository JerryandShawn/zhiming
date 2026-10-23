"""Original X07 observes the real gateway batch, native run and source IDs."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def x07() -> Scenario:
    root = Path(__file__).resolve().parents[3]
    return execution_overlay(next(case for case in load_scenarios(root / "tools/eval/scenarios") if case.id == "X07"))


def test_original_x07_native_run_and_three_sources(target: V4Target) -> None:
    result = evaluate_scenario(x07(), target, target_name="v4")
    assert result["status"] == "passed", result
    snapshot = target.inspect_db()
    runs = [row for row in snapshot["entities"] if row["kind"] == "run"]
    assert len(runs) == 1 and runs[0]["source_store"] == "core_runs"
    assert runs[0]["id"] == target.run_ids[-1] and runs[0]["status"] == "succeeded"
    proof = snapshot["run_meta"]["ingress"]
    assert proof["sent_count"] == 1 and proof["all_input_messages_present"] is True
    assert proof["source_segments_count"] == proof["distinct_timestamps"] == 3
    assert snapshot["run_meta"]["input_message_ids"] == ["fs-one", "fs-two", "fs-three"]
    assert proof["external_channel_sends"] == target.case_evidence()["external_provider_requests"] == 0
    other = "other-synthetic-owner"
    target.repo.ensure_owner(other, settings={"runtime": "v4"})
    threads = ThreadService(target.repo)
    thread = threads.create(other, request_id="other-thread")
    source = threads.receive(other, thread["id"], "隔离来源", request_id="other-source")
    ThreadIngress(target.service).queue(
        owner=other, thread_id=thread["id"], source_ids=[source["id"]], request_id="other-run"
    )
    assert len([row for row in target.inspect_db()["entities"] if row["kind"] == "run"]) == 1


def test_expectations_cannot_supply_batch_source_ids(target: V4Target) -> None:
    data = deepcopy(x07().model_dump(mode="json"))
    data["turns"][0]["expect"]["db"][1]["equals"] = ["forged-source"]
    result = evaluate_scenario(Scenario.model_validate(data), target, target_name="v4")
    assert result["status"] == "failed" and "turn[1].db[2]" in result["failed_assertions"]
    assert target.inspect_db()["run_meta"]["input_message_ids"] == ["fs-one", "fs-two", "fs-three"]

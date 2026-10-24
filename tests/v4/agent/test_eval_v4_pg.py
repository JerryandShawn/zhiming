"""The v4 target observes actual PG effects instead of replaying declared DB rows."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.models.quota_runtime import current_scope
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_target import V4Target

CORPUS = Path(__file__).resolve().parents[3] / "tools/eval/scenarios_v4"


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    send = httpx.Client.send

    def local_only(self, request, *args, **kwargs):
        if request.url.host == "127.0.0.1" and request.url.scheme == "http":
            return send(self, request, *args, **kwargs)
        if request.url.host == "synthetic.invalid" and isinstance(self._transport, httpx.MockTransport):
            return send(self, request, *args, **kwargs)
        raise AssertionError("评测禁止真实供应商HTTP")

    def reject(*args, **kwargs):
        raise AssertionError("评测禁止真实HTTP或子进程")

    monkeypatch.setattr(httpx.Client, "send", local_only)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL15")
    target = V4Target(dsn=dsn)
    try:
        yield target
    finally:
        target.close()


def case(identity: str) -> Scenario:
    return next(item for item in load_scenarios(CORPUS) if item.id == identity)


@pytest.mark.parametrize(
    "identity", ["T01", "T02", "M01", "M03", "M09", "R02", "Q03", "S01", "D01", "X05", "TA01", "TA02", "TA03"]
)
def test_scripted_provider_drives_real_runtime(identity: str, target: V4Target) -> None:
    observed = evaluate_scenario(case(identity), target, target_name="v4")
    assert observed["status"] == "passed", observed
    assert target.repo is not None and target.run_ids
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert run["status"] == "succeeded" and run["runtime"] == "v4"
    assert run["result"]["schema"] == "core4.0"
    if identity == "M03":
        assert [row["data"]["content"] for row in target.inspect_db()["entities"] if row["kind"] == "fact"] == [
            "我不吃辣"
        ]
    if identity == "D01":
        rows = [row for row in target.inspect_db()["entities"] if row["kind"] == "decision_option"]
        assert len(rows) == 2 and all(row["source_store"] == "core_run_steps.output.data.options" for row in rows)
    if identity == "X05":
        proof = target.inspect_db()["evaluator_observations"]
        assert proof[0]["source_store"] == "core_run_steps.output.data.code" and proof[0]["seq"] > 0


def test_wrong_expect_cannot_change_the_observed_model_text(target: V4Target) -> None:
    data = case("T01").model_dump(mode="json")
    wrong = deepcopy(data)
    wrong["turns"][0]["expect"]["must_include_all"] = ["UNPRODUCED_SENTINEL"]
    first = evaluate_scenario(Scenario.model_validate(data), target, target_name="v4")
    failed = evaluate_scenario(Scenario.model_validate(wrong), target, target_name="v4")
    assert first["status"] == "passed" and failed["status"] == "failed"
    assert first["previews"] == failed["previews"] and "must_include_all[1]" in str(failed["failed_assertions"])


def test_x04_measures_quiet_loopback_http_and_persists_interrupted_partial(
    target: V4Target, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, scopes = current_scope(), []
    tick = AgentDispatcher.tick

    def bounded_tick(dispatcher: AgentDispatcher) -> int:
        scopes.append(current_scope())
        return tick(dispatcher)

    def no_permanent_worker(*args, **kwargs):
        raise AssertionError("Synthetic eval must not start a permanent dispatcher")

    monkeypatch.setattr(AgentDispatcher, "tick", bounded_tick)
    monkeypatch.setattr(AgentDispatcher, "start", no_permanent_worker)
    observed = evaluate_scenario(case("X04"), target, target_name="v4")
    assert observed["status"] == "passed", observed
    measured = target.inspect_db()["run_meta"]
    assert 0 <= measured["stop_latency_ms"] < 2000 and measured["scripted_http_requests"] == 1
    assert measured["partial_id"] and measured["rule"].startswith("monotonic")
    assert target.repo.fetch_run(target.owner, measured["run_id"])["status"] == "cancelled"
    assert len(scopes) == 1 and scopes[0].lane == "eval" and scopes[0].scenario_id == "X04"
    assert current_scope() == previous


def test_l01_four_candidate_codecs_roundtrip_real_tools_with_mock_transport(target: V4Target) -> None:
    observed = evaluate_scenario(case("L01"), target, target_name="v4")
    assert observed["status"] == "passed", observed
    proof = target.inspect_db()["portability"]
    assert len(proof["proofs"]) == 4 and not proof["protocol_errors"]
    assert all(row["run_status"] == "succeeded" and row["tool_result_echoes"] >= 1 for row in proof["proofs"])
    assert all(len(row["request_sha256"]) == row["mock_requests"] >= 3 for row in proof["proofs"])


@pytest.mark.parametrize("forged", ["db", "receipt", "event", "meta", "result"])
def test_v4_script_cannot_inject_state_or_events(forged: str, target: V4Target) -> None:
    data = case("T01").model_dump(mode="json")
    values = {"db": {"entities": []}, "receipt": {"write_status": "saved"}, "event": "final", "meta": {}, "result": {}}
    data["scripted"][0]["model"].insert(0, {forged: values[forged]})
    failed = evaluate_scenario(Scenario.model_validate(data), target, target_name="v4")
    assert failed["status"] == "failed" and failed["error_code"] == "ValueError"


def test_target_rejects_remote_stage_or_production_before_connection() -> None:
    for dsn in ("postgresql://x@remote/eval", "postgresql://x@127.0.0.1/live", "postgresql://x@127.0.0.1/stage"):
        with pytest.raises(ValueError):
            V4Target(dsn=dsn)

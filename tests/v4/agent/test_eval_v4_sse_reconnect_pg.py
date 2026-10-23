"""Actual P3 runtime, PG and loopback HTTP prove running disconnect and replay."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path

import httpx
import pytest

from mingjing_core.domain.contracts import ScopeError
from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenario
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_sse_proof import persisted
from tools.eval.targets.v4_target import V4Target

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def sse_target(monkeypatch):
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL")
    # Uvicorn asks the real standard-library platform cache during startup.
    # Resolve it before the subprocess guard; no platform value is substituted.
    platform.uname()
    original_send = httpx.Client.send

    def only_native_get(client, request, *args, **kwargs):
        if (
            request.method != "GET"
            or request.url.scheme != "http"
            or request.url.host != "127.0.0.1"
            or not re.fullmatch(r"/api/runs/run_[a-f0-9]+/events", request.url.path)
            or request.url.username
            or request.url.password
        ):
            raise AssertionError("SSE acceptance only permits its native loopback event GET")
        return original_send(client, request, *args, **kwargs)

    def reject(*args, **kwargs):
        raise AssertionError("SSE acceptance forbids external HTTP and child processes")

    monkeypatch.setattr(httpx.Client, "send", only_native_get)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr("subprocess.run", reject)
    value = V4Target(dsn=dsn)
    try:
        yield value
    finally:
        value.close()


def test_x08_original_contract_observes_actual_running_disconnect_and_complete_replay(sse_target):
    original = load_scenario(ROOT / "tools/eval/scenarios/X08.yaml")
    before = scenario_contract_hash(original)
    scenario = execution_overlay(original)
    assert scenario_contract_hash(scenario) == before
    result = evaluate_scenario(scenario, sse_target, target_name="v4")
    assert result["status"] == "passed", result["failed_assertions"]
    assert scenario_contract_hash(original) == before and result["model_calls"] == 1
    proof = sse_target.case_evidence()["stream"]
    assert proof["all_native_frames_verified"] is True
    assert proof["disconnect_state"]["status"] == "running"
    assert proof["disconnect_state"]["native_ids"] == proof["native_initial_ids"]
    assert proof["native_last_event_id"] == proof["native_initial_ids"][-1]
    assert proof["native_initial_ids"] + proof["native_replay_ids"] == [row["seq"] for row in proof["native_pg_frames"]]
    assert len(set(proof["native_initial_ids"] + proof["native_replay_ids"])) == len(proof["native_pg_frames"])
    native = persisted(sse_target.repo, sse_target.owner, proof["run_id"])
    assert [row["type"] for row in native].count("text_delta") == 2
    assert native[-1]["type"] == "final" and sum(row["type"] == "final" for row in native) == 1
    assert proof["native_replay_ids"][0] > proof["native_last_event_id"]
    assert sse_target.case_evidence()["external_provider_requests"] == 0


def test_persisted_stream_observation_cannot_read_another_owner_or_missing_run(sse_target):
    original = load_scenario(ROOT / "tools/eval/scenarios/X08.yaml")
    sse_target.reset(
        {
            "synthetic": True,
            "_scenario_id": original.id,
            "_scripted": [step.model_dump(exclude_none=True) for step in execution_overlay(original).scripted],
        }
    )
    run = sse_target._request({"_index": 1, "user": "合成事件身份检查", "kind": "chat", "channel": "web"})
    assert persisted(sse_target.repo, sse_target.owner, run["id"]) == []
    with pytest.raises(ScopeError):
        persisted(sse_target.repo, "another-owner", run["id"])
    with pytest.raises(ScopeError):
        persisted(sse_target.repo, sse_target.owner, "run_missing")
    assert sse_target.repo.fetch_run(sse_target.owner, run["id"])["status"] == "running"

"""Real isolated PG/tokenizer plus synthetic HTTP; no real Kimi requests."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from psycopg import sql

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.agent.k3_loader import load_k3_counter
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_r16 import connection_approval
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.timekit.clock import FrozenClock
from tools.eval.k31_connect import run_connection
from tools.eval.k31_contract import SCENARIOS
from tools.eval.k31_control import K31Control, core_approval
from tools.eval.model_selection import ProofSelectedRegistry, selected_model

from .test_delegated_policy import CANDIDATE, NOW
from .test_delegated_quota_pg import central_fixture as central_fixture  # noqa: F401
from .test_k31_first_release import PROFILE, registry
from .test_protocols import recording
from .test_quota_http_pg import adapter, rows
from .test_r16_delegation import fixture_gate


@pytest.fixture(scope="module")
def official_counter():
    return load_k3_counter(Path(os.environ["K3_TOKENIZER_ARTIFACT_DIR"]))


def setup(central):
    guard = QuotaGuard(**central, clock=FrozenClock(NOW))
    approval = connection_approval(fixture_gate()[0], CANDIDATE, NOW)
    control = K31Control(guard.store.dsn, "probe_k31_" + uuid.uuid4().hex)
    control.initialize()
    session = DelegatedSession(guard, approval, phase="k31-connect", scenario_ids=SCENARIOS)
    return guard, approval, control, session


def handler(posted: list):
    def respond(request):
        body = json.loads(request.content)
        assert body["model"] == "k3.1-pro" and body["reasoning_effort"] == "high"
        posted.append(body)
        if len(posted) == 1:
            content = recording(
                {
                    "model": "k3.1-pro",
                    "choices": [
                        {
                            "delta": {
                                "reasoning_content": "合成原始推理",
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "opaque-k31-id",
                                        "function": {"name": "synthetic_echo", "arguments": '{"value":"合成"}'},
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {"prompt_tokens": 10000, "completion_tokens": 5},
                }
            )
        else:
            if len(posted) == 2:
                assistant = body["messages"][-2]
                assert assistant["reasoning_content"] == "合成原始推理"
                assert assistant["tool_calls"][0]["id"] == body["messages"][-1]["tool_call_id"] == "opaque-k31-id"
            text = "合成图书馆故事。" * 200 + "[K31-END]" if len(posted) == 4 else "合成"
            content = recording(
                {
                    "model": "k3.1-pro",
                    "choices": [{"delta": {"content": text}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 10000, "completion_tokens": 2000},
                }
            )
        return httpx.Response(200, content=content)

    return respond


def test_connection_protocol_calibration_and_core_selection_are_bound_to_actual_pg(central, official_counter):
    guard, scripted, control, session = setup(central)
    posted = []
    result = run_connection(
        registry(),
        session,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=httpx.MockTransport(handler(posted)),
    )
    assert result["complete"] and result["mode"] == "mock" and result["model_calls"] == len(posted) == 4
    assert result["wasted_attempt_ids"] == [] and float(result["factor"]) > 1.15
    assert {record["scenario"] for record in result["records"]} == set(SCENARIOS)
    with pytest.raises(GuardRejected):
        core_approval(guard, scripted, result, control)
    # Deliberate synthetic journal promotion ONLY inside this disposable test DB;
    # changing the exported JSON alone must never authorize a core session.
    with control.connect() as connection:
        connection.execute(sql.SQL("UPDATE {} SET mode='live'").format(control.table("probe_sessions")))
    actual = control.report(guard, result["evaluation_session_id"])
    with pytest.raises(GuardRejected):
        core_approval(guard, scripted, {**actual, "factor": "1.15"}, control)
    approval = core_approval(guard, scripted, actual, control)
    with pytest.raises(GuardRejected):
        replace(approval, factor="1.15").check(NOW)
    core = DelegatedSession(guard, approval, phase="core", scenario_ids=["C01"])
    reg = ProofSelectedRegistry(PROFILE, environment={"KIMI_API_KEY": "synthetic-k31-only"})
    with core.activate(), call_scope(core.scope("C01")):
        assert selected_model() == "k3.1-pro" and reg.input_factor == result["factor"]
        assert all(reg.resolve(role)[0].model == "k3.1-pro" for role in ("primary", "critic"))
        with pytest.raises(GuardRejected):
            adapter(guard, lambda _: pytest.fail("old model must not POST")).complete([])
        port = reg.resolve("primary")[0].adapter(guard=guard, transport=httpx.MockTransport(handler(posted)))
        assert port.complete([]).model == "k3.1-pro"
    core.close()
    assert len(rows(guard)) == len(posted) == 5


def test_wrong_actual_model_stops_all_scopes_and_never_replays_connection(central, official_counter):
    guard, _, control, session = setup(central)
    posted = []

    def wrong(request):
        posted.append(1)
        return httpx.Response(
            200,
            content=recording(
                {
                    "model": "k3.1-pro-highspeed",
                    "choices": [{"delta": {"content": "不得使用"}, "finish_reason": "stop"}],
                }
            ),
        )

    meter = K3EstimatedMeter(official_counter, model="k3.1-pro")
    result = run_connection(registry(), session, control, meter, transport=httpx.MockTransport(wrong))
    assert not result["complete"] and result["model_calls"] == 1 and result["records"] == []
    assert result["wasted_attempt_ids"] == result["attempt_ids"] and guard.status()["stop_kind"] == "permission_error"
    assert rows(guard)[0]["status"] == "bad_request"
    assert not run_connection(registry(), session, control, meter, transport=httpx.MockTransport(wrong))["complete"]
    assert len(posted) == 1


def test_operator_cli_missing_central_configuration_is_zero_post(monkeypatch, capsys):
    from tools.eval.k31_cli import main

    for name in ("MEMBER_CENTRAL_DSN", "MEMBER_CENTRAL_SCHEMA", "MEMBER_ACCOUNT_ID", "MEMBER_LEDGER_IDENTITY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PROBE_CONTROL_DSN", os.environ["CORE_TEST_DSN"])
    posted = []

    def deny(*args, **kwargs):
        posted.append(1)
        pytest.fail("missing central configuration must never issue HTTP")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    assert main(["connect", "--control-schema", "probe_r16_missing_configuration"]) == 2
    assert posted == [] and "MEMBER_GUARD_REJECTED" in capsys.readouterr().out

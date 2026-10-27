"""R25 actual HTTP/PG critic retries, and R24 bounded overload classification."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from models.test_delegated_quota_pg import central_fixture as central_fixture  # noqa: F401
from models.test_protocols import recording

from mingjing_core.models.errors import ModelResponseIdentityError
from mingjing_core.models.quota_runtime import call_scope
from tools.eval.engine import evaluate_scenario
from tools.eval.judges import ModelJudge
from tools.eval.k31_results import unavailable_ready
from tools.eval.overload_policy import is_overloaded, overload_due
from tools.eval.quota import ProviderStopped
from tools.eval.report import summarize
from tools.eval.targets.v4_core30 import Core30LiveTarget, load_core30
from tools.eval.targets.v4_live_judge import LiveJudgeProvider, V4LiveJudge
from agent.test_k31_core_chain_pg import core as core  # noqa: F401, F811
from agent.test_k31_core_chain_pg import counter_fixture as counter_fixture  # noqa: F401


def _factory(core, invalid, sent, judge_calls, http_failures=0):  # noqa: F811
    def factory(handle):
        def reply(request):
            body = json.loads(request.content)
            sent.append(body)
            delta = {"reasoning_content": "合成推理"}
            if body.get("tools") and body["tools"][0]["function"]["name"] == "submit":
                assert body["tool_choice"] == "required"
                judge_calls.append(body)
                if len(judge_calls) <= http_failures:
                    return httpx.Response(
                        503, json={"error": {"type": "server_error", "message": "synthetic unavailable"}}
                    )
                if len(judge_calls) <= invalid:
                    delta["content"] = "合成的非工具评分"
                else:
                    delta["tool_calls"] = [
                        {
                            "index": 0,
                            "id": "original",
                            "function": {
                                "name": "submit",
                                "arguments": json.dumps(
                                    {
                                        "score": 1,
                                        "verdict": "pass",
                                        "issues": [],
                                        "reason": "合成契约通过",
                                        "deductions": [],
                                        "expected_clauses": [],
                                    }
                                ),
                            },
                        }
                    ]
            else:
                assert body.get("tool_choice", "auto") == "auto"
                delta["content"] = "今天2026年10月10日星期六，国庆调休工作日，要上班。"
            return httpx.Response(
                200,
                content=recording(
                    {
                        "model": "k3.1-pro",
                        "choices": [
                            {"delta": delta, "finish_reason": "tool_calls" if "tool_calls" in delta else "stop"}
                        ],
                    }
                ),
            )

        return handle.adapter(transport=httpx.MockTransport(reply), guard=core.guard, max_retries=0)

    return factory


@pytest.mark.parametrize("invalid", [0, 1, 2])
def test_native_pg_primary_and_required_judge_retry(core, invalid):  # noqa: F811
    sent = []
    judge_calls = []

    factory = _factory(core, invalid, sent, judge_calls)

    scenario = next(c for c in load_core30() if c.id == "T05")
    with core.session.activate(), call_scope(core.session.scope("T05")):
        target = Core30LiveTarget(
            model="k3.1-pro", dsn=core.guard.store.dsn, environment=core.env, adapter_factory=factory
        )
        judge = V4LiveJudge("k3.1-pro", Path("tools/eval/rubric_v1.md"), environment=core.env, adapter_factory=factory)
        try:
            result = evaluate_scenario(scenario, target, target_name="v4", judge=judge)
            assert len(judge_calls) == min(invalid + 1, 2), {
                "calls": len(sent),
                "judge": len(judge_calls),
                **{
                    k: result.get(k)
                    for k in ["status", "stop_reason", "error_code", "target_error_code", "judge_error_code"]
                },
            }
            assert result["judge_model_calls"] == len(judge_calls)
            if invalid == 2:
                assert result["status"] == "needs_brain_review" and result["score"] is None
                assert result["machine_status"] == "judge_unavailable" and result["needs_brain_review"] is True
                assert summarize([result])["count"] == 0
                assert result["private_evidence"][0]["answer"]
            else:
                assert result["status"] == "passed", result.get("failed_assertions")
                assert result["private_evidence"][0]["judge"]["details"]["reason"]
        finally:
            target.close()


@pytest.mark.parametrize("error", [ProviderStopped("quota", "judge"), ModelResponseIdentityError()])
def test_judge_fatal_signal_never_retries(error):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        raise error

    judge = ModelJudge("synthetic", Path("tools/eval/rubric_v1.md"), SimpleNamespace(generate=generate))
    with pytest.raises(type(error)):
        judge.evaluate({})
    assert len(calls) == 1


@pytest.mark.parametrize("failures", [1, 2])
def test_r38_native_judge_http_retry_then_ungraded(core, failures):  # noqa: F811
    sent, judge_calls = [], []
    factory = _factory(core, 0, sent, judge_calls, http_failures=failures)
    scenario = next(c for c in load_core30() if c.id == "T05")
    with core.session.activate(), call_scope(core.session.scope("T05")):
        target = Core30LiveTarget(
            model="k3.1-pro", dsn=core.guard.store.dsn, environment=core.env, adapter_factory=factory
        )
        judge = V4LiveJudge("k3.1-pro", Path("tools/eval/rubric_v1.md"), environment=core.env, adapter_factory=factory)
        try:
            result = evaluate_scenario(scenario, target, target_name="v4", judge=judge)
            assert len(judge_calls) == 2
            assert result["judge_model_calls"] == 2
            assert result["status"] == ("passed" if failures == 1 else "needs_brain_review"), result.get("stop_reason")
            if failures == 2:
                assert result["score"] is None
                assert result["machine_status"] == "judge_unavailable" and result["needs_brain_review"] is True
        finally:
            target.close()


@pytest.mark.parametrize(
    "reason,status",
    [("provider_http_error", 400), ("provider_http_error", 403), ("quota", 429), ("permission_error", None)],
)
def test_r38_http_or_permission_stop_is_not_converted(reason, status):
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        raise ProviderStopped(reason, "judge", provider_http_status=status)

    provider = object.__new__(LiveJudgeProvider)
    provider.provider = SimpleNamespace(generate=generate)
    provider.tracker = SimpleNamespace(begin_turn=lambda: None, calls=1)
    provider.budget, provider.stop_reason, provider.provider_http_status = None, None, None
    provider.role, provider.elapsed_seconds = "judge", 0.0
    judge = ModelJudge("synthetic", Path("tools/eval/rubric_v1.md"), provider)
    with pytest.raises(ProviderStopped):
        judge.evaluate({})
    assert len(calls) == 1


@pytest.mark.parametrize(
    "status,message,expected",
    [
        (429, "engine_overloaded", True),
        (429, "The engine is currently overloaded", True),
        (429, "服务过载", True),
        (403, "overloaded", False),
        (429, "rate_limit overloaded", False),
        (429, "usage limit", False),
        (429, "concurrency overloaded", False),
        (429, "unknown", False),
    ],
)
def test_r24_explicit_overload_only(status, message, expected):
    assert is_overloaded(status, "", message) is expected


def test_r24_real_timestamps_and_hard_60_minute_bound():
    first = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
    assert overload_due(first, first, 1) == first + timedelta(minutes=1)
    assert overload_due(first, first + timedelta(minutes=5), 6) == first + timedelta(minutes=15)
    assert overload_due(first, first + timedelta(minutes=59), 6) is None
    meta = {
        "unavailable_retry": 0,
        "stopped_at": first.isoformat(),
        "classification_adjudication": {
            "board_version": 33,
            "http_status": 429,
            "message": "engine overloaded",
            "first_overload_at": first.isoformat(),
            "overload_index": 1,
        },
    }
    with pytest.raises(ValueError):
        unavailable_ready(meta, 1, first + timedelta(seconds=59))
    unavailable_ready(meta, 1, first + timedelta(minutes=1))
    with pytest.raises(ValueError):
        unavailable_ready(meta, 1, first + timedelta(minutes=61))


def test_v32_timeout_gate_keeps_quota_rejected():
    stopped = datetime(2026, 10, 24, 13, tzinfo=timezone.utc)
    meta = {
        "unavailable_retry": 0,
        "stopped_at": stopped.isoformat(),
        "classification_adjudication": {
            "board_version": 33,
            "kind": "unavailable",
            "http_status": None,
            "transient_index": 1,
        },
    }
    unavailable_ready(meta, 1, stopped + timedelta(minutes=5))
    meta["classification_adjudication"]["http_status"] = 429
    with pytest.raises(ValueError):
        unavailable_ready(meta, 1, stopped + timedelta(minutes=5))

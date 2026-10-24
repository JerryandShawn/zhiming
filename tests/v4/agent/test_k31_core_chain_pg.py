"""R21 actual PG/Agent/scoring with synthetic HTTP and sealed connection evidence."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from models.test_delegated_policy import CANDIDATE, NOW
from models.test_delegated_quota_pg import central_fixture as central_fixture  # noqa: F401
from models.test_k31_connection_pg import handler, official_counter as original_counter
from models.test_k31_connection_pg import setup
from models.test_k31_first_release import PROFILE, registry
from models.test_protocols import recording
from models.test_quota_http_pg import rows
from psycopg import sql

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_r16 import approved_core_model
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.models.quota_types import GuardRejected
from tools.eval import lifecycle_identity, runner
from tools.eval.engine import evaluate_scenario
from tools.eval.k31_connect import run_connection
from tools.eval.k31_control import core_approval
from tools.eval.lifecycle_identity import LifecycleBinding
from tools.eval.quota_resume_witness import _session
from tools.eval.targets.v4_core30 import Core30LiveTarget, load_core30
from tools.eval.targets.v4_live_judge import V4LiveJudge


@pytest.fixture(scope="module", name="official_counter")
def counter_fixture():
    return original_counter.__wrapped__()


@pytest.fixture
def core(central, official_counter, monkeypatch):
    guard, scripted, control, connect = setup(central)
    probe = handler([])

    def realistic_probe(request):
        response = probe(request)
        # The calibration stress fixture inflates counts; this fixture tests dispatch.
        return httpx.Response(
            200,
            content=response.content.replace(
                b'"prompt_tokens": 10000', b'"prompt_tokens": 100'
            ),
        )

    result = run_connection(
        registry(),
        connect,
        control,
        K3EstimatedMeter(official_counter, model="k3.1-pro"),
        transport=httpx.MockTransport(realistic_probe),
    )
    assert result["complete"]
    # Mock proof is promoted only in this isolated fixture, never by production code.
    with control.connect() as db:
        db.execute(
            sql.SQL("UPDATE {} SET mode='live'").format(control.table("probe_sessions"))
        )
    approval = core_approval(
        guard, scripted, control.report(guard, result["evaluation_session_id"]), control
    )
    monkeypatch.setattr(runner, "_source_digest", lambda: approval.source_sha256)
    monkeypatch.setattr(
        lifecycle_identity, "candidate_provenance", lambda *a: {"worktree_clean": True}
    )
    session = DelegatedSession(guard, approval, phase="core", scenario_ids=["T05"])
    env = {
        "MODELS_CONFIG": str(PROFILE),
        "MINGJING_AGENT_ENABLED": "true",
        "KIMI_API_KEY": "synthetic",
        "K3_TOKENIZER_DIR": str(
            Path(__import__("os").environ["K3_TOKENIZER_ARTIFACT_DIR"])
        ),
    }
    env.update(
        {
            "MEMBER_CENTRAL_DSN": guard.store.dsn,
            "MEMBER_CENTRAL_SCHEMA": guard.store.schema,
            "MEMBER_ACCOUNT_ID": guard.store.account_id,
            "MEMBER_LEDGER_IDENTITY": guard.store.identity,
        }
    )
    yield SimpleNamespace(guard=guard, session=session, env=env)
    session.close()


def native_reply(body):
    delta = {"reasoning_content": "合成推理"}
    if any(
        t.get("function", {}).get("name") == "submit" for t in body.get("tools", [])
    ):
        delta["tool_calls"] = [
            {
                "index": 0,
                "id": "judge-original",
                "function": {
                    "name": "submit",
                    "arguments": json.dumps(
                        {"score": 1, "verdict": "pass", "issues": []}
                    ),
                },
            }
        ]
    else:
        delta["content"] = "今天是2026年10月10日，星期六。合成已核对。"
    return httpx.Response(
        200,
        content=recording(
            {
                "model": "k3.1-pro",
                "choices": [
                    {
                        "delta": delta,
                        "finish_reason": "tool_calls"
                        if "tool_calls" in delta
                        else "stop",
                    }
                ],
            }
        ),
    )


def test_k31_actual_core_lifecycle_primary_and_external_score(core):
    case = next(c for c in load_core30() if c.id == "T05")
    posted = []

    def factory(handle):
        assert handle.model == "k3.1-pro"

        def respond(request):
            body = json.loads(request.content)
            assert body["model"] == "k3.1-pro" and body["reasoning_effort"] == "high"
            posted.append(body)
            return native_reply(body)

        return handle.adapter(
            transport=httpx.MockTransport(respond), guard=core.guard, max_retries=0
        )

    with core.session.activate(), call_scope(core.session.scope(case.id)):
        binding = LifecycleBinding.capture(core.guard, CANDIDATE, case, "k3.1-pro")
        assert binding.verify(core.guard)["model"] == "k3.1-pro"
        assert (
            _session(SimpleNamespace(model="k3.1-pro"), binding, core.guard)
            is core.session
        )
        target = Core30LiveTarget(
            model="k3.1-pro",
            dsn=core.guard.store.dsn,
            environment=core.env,
            adapter_factory=factory,
        )
        judge = V4LiveJudge(
            "k3.1-pro",
            Path("tools/eval/rubric_v1.md"),
            environment=core.env,
            adapter_factory=factory,
        )
        try:
            result = evaluate_scenario(case, target, target_name="v4", judge=judge)
            assert "stop_reason" not in result and "target_error_code" not in result, {
                k: result.get(k)
                for k in [
                    "stop_reason",
                    "target_error_code",
                    "judge_error_code",
                    "model_calls",
                ]
            }
            assert result["target_model_calls"] == result["judge_model_calls"] == 1
            assert len(posted) == 2 and result["score"] is not None
            assert any(
                x.get("stage") == "agent_model_attempts"
                for x in target.repo.list(target.owner, "runtime_step")
            )
            assert len(rows(core.guard)) == 6
        finally:
            target.close()


def test_k31_binding_requires_matching_sealed_core_proof(core):
    case = load_core30()[0]
    with pytest.raises(GuardRejected):
        LifecycleBinding.capture(core.guard, CANDIDATE, case, "k3.1-pro")
    with core.session.activate():
        with pytest.raises(ValueError):
            LifecycleBinding.capture(core.guard, "b" * 40, case, "k3.1-pro")
    with pytest.raises(GuardRejected):
        approved_core_model(replace(core.session.approval, source_sha256="f" * 64), NOW)


def test_k31_quota_stop_restarts_whole_question_with_fresh_run(core):
    from datetime import timedelta
    from mingjing_core.models.quota_delegated import resume_delegated

    case = load_core30()[0]
    posted = []
    quota = True

    def factory(handle):
        def respond(request):
            body = json.loads(request.content)
            posted.append(body)
            if quota:
                return httpx.Response(
                    429,
                    headers={"Retry-After": "18000"},
                    json={
                        "error": {
                            "type": "permission_error",
                            "message": "5-hour usage limit",
                        }
                    },
                )
            return native_reply(body)

        return handle.adapter(
            transport=httpx.MockTransport(respond), guard=core.guard, max_retries=0
        )

    with core.session.activate(), call_scope(core.session.scope(case.id)):
        first = Core30LiveTarget(
            model="k3.1-pro",
            dsn=core.guard.store.dsn,
            environment=core.env,
            adapter_factory=factory,
        )
        try:
            stopped = evaluate_scenario(case, first, target_name="v4")
            old_run = first.run_ids[0]
            assert stopped["status"] == "incomplete" and stopped["score"] is None
            assert (
                stopped["stop_reason"] == "quota_5h"
                and stopped["automatic_resume_eligible"]
            )
            assert len(posted) == 1
        finally:
            first.close()
    with pytest.raises(GuardRejected):
        resume_delegated(core.guard, core.session.approval)
    core.guard.clock.advance(timedelta(hours=5))
    assert resume_delegated(core.guard, core.session.approval)
    core.session.close()
    quota = False
    fresh = DelegatedSession(
        core.guard, core.session.approval, phase="core", scenario_ids=[case.id]
    )
    with fresh.activate(), call_scope(fresh.scope(case.id)):
        target = Core30LiveTarget(
            model="k3.1-pro",
            dsn=core.guard.store.dsn,
            environment=core.env,
            adapter_factory=factory,
        )
        try:
            restarted = evaluate_scenario(case, target, target_name="v4")
            assert (
                "stop_reason" not in restarted and "target_error_code" not in restarted
            )
            assert target.run_ids[0] != old_run and len(posted) == 2
        finally:
            target.close()
            fresh.close()


def test_k31_recovery_token_stage_matches_native_delegation(core):
    from mingjing_core.models.quota_delegated import delegated_stage
    from mingjing_core.models.quota_r16 import core_token_stage

    assert (
        core_token_stage("k3.1-pro")
        == delegated_stage(core.session.approval, "core")
        == "core-k31"
    )
    assert core_token_stage("k3") == "core-k3"
    assert core_token_stage("k3-256k") == "core-k3-256k"
    with pytest.raises(GuardRejected):
        core_token_stage("k3.1-pro-highspeed")

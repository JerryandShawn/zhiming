"""Actual Agent/U4/local K3/PG with only provider HTTP and external delivery substituted."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from models.test_delegated_policy import synthetic_approval
from models.test_quota_guard_pg import configure_central
from models.test_quota_http_pg import rows
from models.test_u39_anthropic_wire import block_record
from psycopg import sql

from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.registry import ModelHandle
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.engine import _record_stop, evaluate_scenario
from tools.eval.live import candidate_provenance
from tools.eval.schema import Scenario
from tools.eval.targets.v4_live import V4LiveTarget
from tools.eval.targets.v4_live_judge import V4LiveJudge

ROOT = Path(__file__).resolve().parents[3]


def wire(*blocks: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, content=block_record(list(blocks)))


def scenario(*, channel: str = "web", turns: int = 1, memory: bool = False) -> Scenario:
    text = "下周一要面试" if memory else "合成过去日期问题"
    expect = {"must_include_all": ["合成已核对"]}
    if memory:
        expect = {
            "receipts": [{"write_status": "saved"}],
            "db": [{"kind": "fact", "where": {"data.event_at": "2025-01-06"}, "count": 1}],
        }
    return Scenario.model_validate(
        {
            "id": "M01" if memory else "T01",
            "title": "合成真实Agent连接",
            "category": "memory_write" if memory else "time",
            "clock": "2025-01-01T10:30:00+08:00",
            "seed": {"profile": "empty_profile"},
            "turns": [{"user": text, "channel": channel, "expect": expect} for _ in range(turns)],
            "scripted": [{"turn": i, "model": [{"text": "UNPRODUCED_SCRIPT_SENTINEL"}]} for i in range(1, turns + 1)],
        }
    )


@dataclass
class Harness:
    guard: QuotaGuard
    environment: dict[str, str]
    session: DelegatedSession
    sent: list[httpx.Request] = field(default_factory=list)
    targets: list[V4LiveTarget] = field(default_factory=list)
    primary: Callable[[httpx.Request], httpx.Response] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        body = json.loads(request.content)
        if any(tool["name"] == "submit" for tool in body.get("tools", [])):
            return wire(
                {
                    "type": "tool_use",
                    "id": "judge-mock",
                    "name": "submit",
                    "input": {
                        "score": 1.0,
                        "verdict": "pass",
                        "issues": [],
                        "reason": "合成回答符合期望",
                        "deductions": [],
                        "expected_clauses": [],
                    },
                }
            )
        return self.primary(request) if self.primary else wire({"type": "text", "text": "合成已核对"})

    def factory(self, handle: ModelHandle):
        return handle.adapter(transport=httpx.MockTransport(self.handle), guard=self.guard, max_retries=0)

    def target(self, *, model: str = "k3-256k") -> V4LiveTarget:
        target = V4LiveTarget(
            model=model,
            dsn=os.environ["CORE_TEST_DSN"],
            environment=self.environment,
            adapter_factory=self.factory,
        )
        self.targets.append(target)
        return target

    def judge(self) -> V4LiveJudge:
        return V4LiveJudge(
            "k3-256k",
            ROOT / "tools/eval/rubric_v1.md",
            environment=self.environment,
            adapter_factory=self.factory,
        )


@pytest.fixture
def live(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    configured = os.getenv("K3_TOKENIZER_ARTIFACT_DIR")
    directory = (
        Path(configured) if configured else ROOT.parent / "zhiming-v4/private/artifacts/kimi-k3-installer-20261023"
    )
    if configured:
        assert directory.is_dir(), "CONFIGURED_OFFICIAL_K3_ARTIFACTS_REQUIRED"
    if not directory.is_dir():
        pytest.skip("requires previously installed official public K3 files; tests never download")
    central = configure_central(p2_repo, monkeypatch)
    guard = QuotaGuard(**central)
    approved = synthetic_approval(equivalent=True)
    environment = {
        "MINGJING_AGENT_ENABLED": "true",
        "MODELS_CONFIG": str(ROOT / "config/models.yaml"),
        "K3_TOKENIZER_DIR": str(directory),
        "KIMI_API_KEY": "synthetic-live-evaluation-only",
        "KIMI_BASE_URL": "https://synthetic.invalid/v1",
        **{
            name: central[key]
            for key, name in {
                "central_dsn": "MEMBER_CENTRAL_DSN",
                "central_schema": "MEMBER_CENTRAL_SCHEMA",
                "account_id": "MEMBER_ACCOUNT_ID",
                "ledger_identity": "MEMBER_LEDGER_IDENTITY",
            }.items()
        },
    }
    original = httpx.Client.send

    def only_mock(client, request, *args, **kwargs):
        if not isinstance(client._transport, httpx.MockTransport):
            raise AssertionError("live adapter tests allow only MockTransport")
        return original(client, request, *args, **kwargs)

    monkeypatch.setattr(httpx.Client, "send", only_mock)
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
        monkeypatch.setenv(key, "1")
    session = DelegatedSession(guard, approved, phase="core", scenario_ids=["T01", "M01"])
    harness = Harness(guard, environment, session)
    try:
        yield harness
    finally:
        for target in harness.targets:
            target.close()
        session.close()


def test_actual_agent_u4_meter_and_wallclock_are_used(live: Harness) -> None:
    target = live.target()
    count = 0

    def answer(request: httpx.Request) -> httpx.Response:
        nonlocal count
        count += 1
        if count == 1:
            return wire(
                {
                    "type": "tool_use",
                    "id": "memory-mock",
                    "name": "memory_write",
                    "input": {
                        "message_id": target.bindings["turn-1"],
                        "quote": "下周一要面试",
                        "summary": "合成面试",
                        "kind": "event",
                        "date_expression": "下周一",
                    },
                }
            )
        return wire({"type": "text", "text": "合成已核对"})

    live.primary = answer
    with live.session.activate():
        observed = evaluate_scenario(scenario(memory=True), target, target_name="v4", judge=live.judge())
    assert observed["status"] == "passed", {key: observed.get(key) for key in ("error_code", "failed_assertions")}
    assert observed["target_model_calls"] == 2 and observed["judge_model_calls"] == 1
    records = rows(live.guard)
    assert len(records) == len(live.sent) == 3 and [row["role"] for row in records] == [
        "primary",
        "primary",
        "critic",
    ]
    assert all(row["lane"] == "eval" and row["scenario_id"] == "M01" for row in records)
    assert all(row["at"].year == 2026 for row in records)
    assert all(row["run_id"] == target.run_ids[-1] for row in records if row["role"] == "primary")
    assert target.runtime.offline is False and target.runtime.meter.live_admissible
    assert target.runtime.reviewer.port is None and target.case_evidence()["external_provider_requests"] == 0
    assert "UNPRODUCED_SCRIPT_SENTINEL" not in json.dumps(observed)


def test_six_turns_and_external_judge_roll_at_ten_physical_calls(live: Harness) -> None:
    target = live.target()
    with live.session.activate():
        observed = evaluate_scenario(scenario(turns=6), target, target_name="v4", judge=live.judge())
    assert observed["status"] == "passed" and observed["model_calls"] == 12
    records = rows(live.guard)
    assert len(records) == len(live.sent) == 12
    counts = [
        sum(row["batch_id"] == ident for row in records) for ident in dict.fromkeys(row["batch_id"] for row in records)
    ]
    assert counts == [10, 2] and live.guard.status()["in_flight"] == 0


def test_absent_delegation_stops_before_any_http(live: Harness) -> None:
    observed = evaluate_scenario(scenario(), live.target(), target_name="v4", judge=live.judge())
    assert observed["stop_reason"] == "manual_start_required"
    assert observed["model_calls"] == 0 and not live.sent and not rows(live.guard)


def test_requested_model_cannot_silently_use_different_config(live: Harness) -> None:
    with live.session.activate():
        observed = evaluate_scenario(scenario(), live.target(model="k3"), target_name="v4")
    assert observed["status"] == "failed" and observed["error_code"] == "ValueError"
    assert not live.sent and not rows(live.guard)


@pytest.mark.parametrize(
    "kind,message",
    [
        ("permission_error", "synthetic private permission"),
        ("access_terminated", "Access terminated"),
        ("quota_5h", "You've reached your 5-hour usage limit."),
        ("concurrency_limited", "Too many concurrent requests"),
    ],
)
def test_provider_stop_cannot_be_swallowed_by_agent_or_continue_to_judge(
    live: Harness, kind: str, message: str
) -> None:
    live.primary = lambda _: httpx.Response(403, json={"error": {"type": "permission_error", "message": message}})
    with live.session.activate():
        observed = evaluate_scenario(scenario(turns=2), live.target(), target_name="v4", judge=live.judge())
    assert observed["stop_reason"] == kind and observed["target_model_calls"] == 1
    assert observed["judge_model_calls"] == 0 and len(live.sent) == len(rows(live.guard)) == 1
    assert "synthetic private" not in json.dumps(observed)
    assert observed["permanent_stop"] is (kind == "access_terminated")


def test_preexisting_stop_reports_zero_new_attempts(live: Harness) -> None:
    live.guard.record_stop("access_terminated")
    with live.session.activate():
        observed = evaluate_scenario(scenario(), live.target(), target_name="v4")
    assert observed["stop_reason"] == "access_terminated" and observed["model_calls"] == 0
    assert not live.sent and not rows(live.guard)


def test_native_feishu_delivery_is_only_local_transport(live: Harness) -> None:
    target = live.target()
    with live.session.activate():
        observed = evaluate_scenario(scenario(channel="feishu"), target, target_name="v4")
    assert observed["status"] == "passed" and len(target.feishu.sent) == 1
    with target.repo.transaction(target.owner) as connection:
        count = connection.execute(
            sql.SQL("SELECT count(*) AS n FROM {}").format(target.repo.table("delivery_outbox"))
        ).fetchone()["n"]
    assert count == 1 and target.case_evidence()["external_provider_requests"] == 0


@pytest.mark.parametrize(
    "reset,eligible",
    [(None, False), ("not a timestamp", False), ("2026-10-24T00:00:00+08:00", True)],
)
def test_only_known_aware_quota_reset_is_resume_eligible(reset: str | None, eligible: bool) -> None:
    case = {}
    _record_stop(case, "quota_5h", "target", 403, reset)
    assert case["automatic_resume_eligible"] is eligible and case["requires_user_decision"] is not eligible
    assert ("resume_at" in case) is eligible


def test_candidate_provenance_is_actual_head_and_clean_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(["a" * 40 + "\n", ""])
    monkeypatch.setattr(
        "tools.eval.live.subprocess.check_output",
        lambda *args, **kwargs: next(responses),
    )
    assert candidate_provenance(ROOT, "a" * 40) == {
        "candidate_commit": "a" * 40,
        "worktree_clean": True,
    }

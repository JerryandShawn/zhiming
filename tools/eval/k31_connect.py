"""Bounded R16 execution; the caller is Claude, tests replace only HTTP."""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal
from typing import Any

import httpx

from mingjing_core.agent.context_k3 import calibration
from mingjing_core.agent.context_tokens import measure_request
from mingjing_core.models.metering import request_meter
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_runtime import call_scope
from tools.eval.k31_contract import CASES, MODEL, SCENARIOS, contract_digest, followup
from tools.eval.k31_control import K31Control
from tools.probe_equivalence_control import ProbeControlError
from tools.probe_k3_equivalence import check_response


def check_profile(registry):
    for role in ("primary", "critic", "evaluation"):
        handles = registry.resolve(role)
        if len(handles) != 1 or any(
            handle.model != MODEL
            or handle.provider != "kimi_code"
            or handle.protocol != "openai_compat"
            or handle.base_url.rstrip("/") != "https://api.kimi.com/coding/v1"
            or handle.settings.get("membership") is not True
            or handle.settings.get("model_lock") != MODEL
            or handle.settings.get("effort") != "high"
            or handle.settings.get("reasoning_effort") != "high"
            or handle.caps.get("reasoning_replay") is not True
            or handle.caps.get("tools") is not True
            or handle.caps.get("include_usage") is not True
            for handle in handles
        ):
            raise ProbeControlError("R16只允许固定官方端点的精确k3.1-pro及显式high")
    return registry.resolve("evaluation")[0]


def public_result(case, step, response, measured, actual: int) -> dict:
    estimated = measured.estimated_input_tokens
    if type(estimated) is not int or estimated <= 0 or type(actual) is not int or actual <= 0:
        raise ProbeControlError("实际输入计量缺失")
    passed = check_response(case, response, final=step == 2)
    if case.ident == "K31-TOOLS" and step == 1:
        passed = passed and bool(response.reasoning) and response.reasoning_present
    if case.ident == "K31-LONG":
        passed = (
            not response.tool_calls
            and len(re.findall(r"[\u4e00-\u9fff]", response.text)) >= 1000
            and response.text.rstrip().endswith("[K31-END]")
        )
    passed = passed and response.model == MODEL and response.execution_meta.get("effort_source") == "explicit_request"
    return {
        "model": MODEL,
        "scenario": case.ident,
        "step": step,
        "passed": bool(passed),
        "response_model": response.model,
        "effort": response.execution_meta.get("effort"),
        "reasoning_present": response.reasoning_present,
        "text_chars": len(response.text),
        "tool_count": len(response.tool_calls),
        "input_actual": actual,
        "input_estimated": estimated,
        "input_ratio": str(Decimal(actual) / Decimal(estimated)),
        "factor": calibration({}, measured, actual)["factor"],
    }


class ConnectionExecution:
    def __init__(self, adapter: Any, session: DelegatedSession, control: K31Control, identity: str, meter: Any):
        self.adapter, self.session, self.control, self.identity, self.meter = adapter, session, control, identity, meter
        self.attempt: str | None = None

    def before(self, run_id: str) -> None:
        pending = [
            row
            for row in self.control.physical(self.session.guard)
            if row["run_id"] == run_id and row["finished_at"] is None
        ]
        if len(pending) != 1:
            raise ProbeControlError("R16物理预留不唯一")
        self.attempt = pending[0]["attempt_id"]

    def step(self, case, step: int, messages: list):
        run_id = f"{self.identity}:{MODEL}:{case.ident}:{step}"
        choice = "required" if case.tools and step == 1 else "auto"
        measured = measure_request(tuple(messages), case.tools, self.meter, tool_choice=choice)
        self.attempt = None
        scope = replace(self.session.scope(case.ident), run_id=run_id)
        with call_scope(scope), request_meter(lambda: self.before(run_id)):
            response = self.adapter.complete(
                messages,
                tools=list(case.tools),
                tool_choice=choice,
                role="evaluation",
                max_output=8192,
            )
        physical = next(
            (row for row in self.control.physical(self.session.guard) if row["attempt_id"] == self.attempt), None
        )
        if physical is None:
            raise ProbeControlError("R16没有实际物理预留")
        result = public_result(case, step, response, measured, physical["input_tokens"])
        self.control.record(self.session.guard, self.identity, self.attempt, result)
        if not result["passed"]:
            raise ProbeControlError("R16接入检查未通过；保留结果，不自动重试或降级")
        return response


def run_connection(registry, session: DelegatedSession, control: K31Control, meter, *, transport=None) -> dict:
    if session.phase != "k31-connect" or session.scenarios != SCENARIOS:
        raise ProbeControlError("R16仅执行固定接入计划")
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ProbeControlError("离线传输必须为MockTransport")
    base = check_profile(registry)
    if transport is None and meter.live_admissible is not True:
        raise ProbeControlError("R16缺少固定本机分词器")
    with control.exclusive(session.guard):
        row = control.open_session(
            session.guard,
            session.approval.candidate,
            session.approval.source_sha256,
            contract_digest(),
            "mock" if transport is not None else "live",
        )
        identity = row["evaluation_session_id"]
        # Never resume a partly completed tool cycle or repeat a completed probe.
        if (
            row["status"] != "active"
            or control.checks(identity)
            or any(
                (physical["run_id"] or "").startswith(identity + ":") for physical in control.physical(session.guard)
            )
        ):
            return control.report(session.guard, identity)
        execution = ConnectionExecution(
            base.adapter(guard=session.guard, max_retries=0, transport=transport),
            session,
            control,
            identity,
            meter,
        )
        try:
            with session.activate():
                for case in CASES:
                    messages = case.messages()
                    first = execution.step(case, 1, messages)
                    if case.roundtrip:
                        execution.step(case, 2, messages + followup(first))
            control.mark(session.guard, identity, "complete")
        except Exception as error:
            control.mark(session.guard, identity, "stopped", getattr(error, "kind", "connection_check_failed"))
        finally:
            session.close()
        return control.report(session.guard, identity)

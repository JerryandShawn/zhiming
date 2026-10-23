"""Fixed v7 probe with PG checkpoints; importing or initialization sends nothing."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import httpx

from mingjing_core.models.metering import request_meter
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.quota_delegated import resume_delegated
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_runtime import CentralLocation, call_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import ModelRegistry
from tools.eval.targets.local_db import verify_local_postgres
from tools.member_delegate import candidate_gate
from tools.probe_equivalence_cases import CASES, MAX_ATTEMPTS, SCENARIOS, EquivalenceCase
from tools.probe_equivalence_control import ProbeControl, ProbeControlError
from tools.probe_equivalence_proof import MODELS, contract_digest, proof_report


def make_adapter(base: Any, case: EquivalenceCase, guard: Any, transport_factory: Any) -> Any:
    transport = transport_factory(case) if transport_factory is not None else None
    if transport is not None and not isinstance(transport, httpx.MockTransport):
        raise ProbeControlError("测试传输必须为纯替身")
    return base.adapter(max_retries=0, guard=guard, transport=transport)


class ProbeExecution:
    def __init__(
        self,
        base: Any,
        session: DelegatedSession,
        control: ProbeControl,
        identity: str,
        transport_factory: Callable | None,
    ) -> None:
        self.base, self.session, self.control = base, session, control
        self.identity, self.transport_factory = identity, transport_factory
        self.current_attempt: str | None = None

    def before(self, run_id: str) -> None:
        physical = self.control.physical(self.session.guard)
        if len(physical) > MAX_ATTEMPTS:
            raise GuardRejected("delegation_request_limit")
        pending = [row for row in physical if row["run_id"] == run_id and row["finished_at"] is None]
        if len(pending) != 1:
            raise ProbeControlError("物理预留不唯一")
        self.current_attempt = pending[0]["attempt_id"]

    def step(self, adapter: Any, case: EquivalenceCase, model: str, messages: list, index: int) -> Any:
        from tools.probe_k3_equivalence import public_result

        run_id = f"{self.identity}:{model}:{case.ident}:{index + 1}"
        scope = replace(self.session.scope(case.ident), run_id=run_id)
        self.current_attempt = None
        with call_scope(scope), request_meter(lambda: self.before(run_id)):
            started = time.monotonic()
            response = adapter.complete(
                messages,
                tools=list(case.tools),
                tool_choice="required" if index == 0 and case.tools else "auto",
                role="evaluation",
                max_output=512,
            )
        result = public_result(model, case, response, time.monotonic() - started, final=index == 1)
        if self.current_attempt is None:
            raise ProbeControlError("没有实际物理预留")
        self.control.record(self.session.guard, self.identity, self.current_attempt, result)
        return response

    def case(self, case: EquivalenceCase, model: str) -> None:
        from tools.probe_k3_equivalence import CAPS

        existing = {
            row["step"]
            for row in self.control.checks(self.identity)
            if row["model"] == model and row["scenario"] == case.ident
        }
        expected = {1, 2} if case.roundtrip else {1}
        if existing == expected:
            return
        if existing:
            raise ProbeControlError("缺少私有多轮状态，不能重放已完成请求")
        if len(self.control.physical(self.session.guard)) >= MAX_ATTEMPTS:
            raise GuardRejected("delegation_request_limit")
        settings = {key: value for key, value in self.base.settings.items() if key != "model_lock"}
        handle = replace(self.base, model=model, caps=CAPS, settings=settings)
        adapter = make_adapter(handle, case, self.session.guard, self.transport_factory)
        messages = case.messages()
        for index in range(2 if case.roundtrip else 1):
            response = self.step(adapter, case, model, messages, index)
            if case.roundtrip and index == 0:
                messages.append(response.as_chat(tool_cycle="synthetic-equivalence-cycle"))
                messages.extend(
                    ChatMessage(
                        "tool",
                        json.dumps({"value": "合成"}, ensure_ascii=False),
                        tool_call_id=call.id,
                        tool_cycle="synthetic-equivalence-cycle",
                    )
                    for call in response.tool_calls
                )


def _continue(control: ProbeControl, session: DelegatedSession, row: dict, *, resume: bool) -> bool:
    physical, checks = control.physical(session.guard), control.checks(row["evaluation_session_id"])
    state = session.guard.status()
    if row["prior_attempt_ids"] or len(physical) + MAX_ATTEMPTS - len(checks) > MAX_ATTEMPTS:
        control.mark(
            session.guard, row["evaluation_session_id"], "incomplete", state["stop_kind"] or "budget_insufficient"
        )
        return False
    if state["stop_kind"]:
        if not resume or state["stop_kind"] != "quota_5h" or state["resume_at"] is None:
            return False
        if session.guard.clock.now() < state["resume_at"]:
            return False
        resume_delegated(session.guard, session.approval)
    return True


def run_delegated(
    base: Any,
    session: DelegatedSession,
    control: ProbeControl,
    *,
    source_sha256: str,
    transport_factory: Callable | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    if session.phase != "equivalence" or tuple(session.scenarios) != SCENARIOS:
        raise ProbeControlError("必须执行原九场景两模型固定合同")
    with control.exclusive(session.guard):
        row = control.open_session(
            session.guard,
            session.approval.candidate,
            source_sha256,
            contract_digest(),
            "mock" if transport_factory is not None else "live",
        )
        identity = row["evaluation_session_id"]
        existing = proof_report(control, session.guard, identity)
        if existing["complete"] or not _continue(control, session, row, resume=resume):
            return proof_report(control, session.guard, identity)
        execution = ProbeExecution(base, session, control, identity, transport_factory)
        try:
            with session.activate():
                for case in CASES:
                    for model in MODELS:
                        execution.case(case, model)
            control.mark(session.guard, identity, "complete")
        except Exception as error:
            control.mark(session.guard, identity, "stopped", getattr(error, "kind", "probe_incomplete"))
        finally:
            session.close()
        return proof_report(control, session.guard, identity)


def _base() -> Any:
    handles = [item for item in ModelRegistry().resolve("evaluation") if item.provider == "kimi_code"]
    if (
        len(handles) != 1
        or handles[0].base_url.rstrip("/") != "https://api.kimi.com/coding/v1"
        or handles[0].protocol != "anthropic_messages"
    ):
        raise ProbeControlError("只允许既定Kimi Code会员协议")
    return handles[0]


def delegated_cli(args: Any) -> int:
    control = ProbeControl(os.environ.get(args.control_dsn_env, ""), args.control_schema)
    if control.schema == os.environ.get("MEMBER_CENTRAL_SCHEMA"):
        raise ProbeControlError("评测控制schema不能复用中央schema")
    if args.mode == "init-control":
        if not args.init_control_schema:
            raise ProbeControlError("初始化需要显式参数")
        control.initialize()
        print(json.dumps({"ok": True, "initialized": True, "model_calls": 0}))
        return 0
    if args.init_control_schema or args.output is None or args.output.exists() or not args.output.parent.is_dir():
        raise ProbeControlError("正常评测不初始化schema，输出必须为新文件")
    location = CentralLocation.from_environment()
    verify_local_postgres(location.central_dsn)
    guard = location.guard()
    approval = candidate_gate(args.scripted_gate, args.candidate, guard.clock.now())
    from tools.eval.runner import _source_digest

    session = DelegatedSession(guard, approval, phase="equivalence", scenario_ids=SCENARIOS)
    result = run_delegated(_base(), session, control, source_sha256=_source_digest(), resume=args.resume)
    try:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
    except OSError:
        print(json.dumps({"ok": False, "code": "PROBE_REPORT_WRITE_FAILED", "model_calls": result["model_calls"]}))
        return 2
    print(json.dumps({key: result[key] for key in ("complete", "equivalent", "model_calls", "stop_kind")}))
    return 0 if result["complete"] else 2

"""Bounded k3/k3-256k capability comparison; default is a local wire rehearsal."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator

from mingjing_core.models.metering import request_meter
from mingjing_core.models.port import AssistantMessage, ChatMessage
from mingjing_core.models.quota_runtime import CallScope, CentralLocation, call_scope
from mingjing_core.models.registry import ModelHandle, ModelRegistry
from mingjing_core.timekit.clock import get_clock
from tools.probe_equivalence_cases import CASES, MAX_ATTEMPTS, SCENARIOS, EquivalenceCase
from tools.probe_equivalence_mock import mock_transport

MODELS = ("k3", "k3-256k")
CAPS = {"tools": True, "tool_choice": ["auto", "required"], "reasoning_replay": True}


class ProbeRejected(ValueError):
    code = "EQUIVALENCE_PROBE_REJECTED"


class Counter:
    def __init__(self) -> None:
        self.attempts = 0

    def before(self) -> None:
        if self.attempts >= MAX_ATTEMPTS:
            raise ProbeRejected("已达到二十次请求上限，不重试")
        self.attempts += 1


def check_response(case: EquivalenceCase, response: AssistantMessage, *, final: bool = False) -> bool:
    tools = {tool.name: tool for tool in case.tools}
    if tools and not final:
        names = [call.name for call in response.tool_calls]
        if len(names) != len(tools) or set(names) != set(tools):
            return False
        try:
            for call in response.tool_calls:
                Draft202012Validator(tools[call.name].parameters).validate(call.arguments)
        except Exception:
            return False
        return True
    if response.tool_calls or not response.text.strip():
        return False
    if case.ident == "EQ03":
        return bool(response.usage)
    if case.ident == "EQ02":
        return "2026-10-17" in response.text and any(word in response.text for word in ("周六", "星期六"))
    if case.ident == "EQ08":
        try:
            return json.loads(response.text) == {"ok": True}
        except ValueError:
            return False
    return "合成" in response.text


def public_result(
    model: str, case: EquivalenceCase, response: AssistantMessage, elapsed: float, *, final: bool
) -> dict:
    identity = response.model if re.fullmatch(r"[A-Za-z0-9._:-]{1,80}", response.model or "") else "unknown"
    usage = {
        key: value
        for key, value in response.usage.items()
        if key in {"input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"}
        and type(value) is int
        and value >= 0
    }
    return dict(
        model=model,
        scenario=case.ident,
        step=2 if final else 1,
        passed=check_response(case, response, final=final),
        response_model=identity,
        text_chars=len(response.text),
        tool_count=len(response.tool_calls),
        reasoning_present=response.reasoning_present,
        usage=usage,
        usage_known=bool(usage),
        elapsed_ms=round(elapsed * 1000, 3),
        effort=response.execution_meta.get("effort", "unknown"),
    )


def execute_case(handle: ModelHandle, case: EquivalenceCase, counter: Counter, *, mock: bool, grant: Any) -> list[dict]:
    seen: list[dict] = []
    adapter = handle.adapter(max_retries=0, transport=mock_transport(case, seen) if mock else None)
    messages = case.messages()
    records = []
    scope = grant.scope(case.ident) if grant else CallScope()
    with call_scope(scope), request_meter(counter.before):
        for index in range(2 if case.roundtrip else 1):
            started = time.monotonic()
            response = adapter.complete(
                messages,
                tools=list(case.tools),
                tool_choice="required" if index == 0 and case.tools else "auto",
                role="evaluation",
                max_output=512,
            )
            record = public_result(handle.model, case, response, time.monotonic() - started, final=index == 1)
            records.append(record)
            if not record["passed"]:
                raise ProbeRejected("协议或合成能力检查未通过，已停止且不重试")
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
    return records


def configuration(live: bool, grant_path: Path | None) -> tuple[ModelHandle, Any, Any]:
    if not live:
        return (
            ModelHandle(
                "synthetic-equivalence",
                "kimi_code",
                "k3-256k",
                "anthropic_messages",
                "https://api.kimi.com/coding/v1",
                "synthetic-offline-credential",
                CAPS,
                {"membership": True, "role_binding": "evaluation"},
                role="evaluation",
            ),
            None,
            None,
        )
    if grant_path is None:
        raise ProbeRejected("真实探针需要用户在线创建的本批授权")
    from tools.manual_grant import load_manual_grant

    grant = load_manual_grant(grant_path, suite="PROBE", scenario_ids=list(SCENARIOS))
    guard = CentralLocation.from_environment().guard()
    handles = [item for item in ModelRegistry().resolve("evaluation") if item.provider == "kimi_code"]
    if len(handles) != 1 or handles[0].base_url.rstrip("/") != "https://api.kimi.com/coding/v1":
        raise ProbeRejected("只允许既定Kimi Code会员端点")
    return handles[0], guard, grant


def run(*, live: bool = False, grant_path: Path | None = None) -> dict[str, Any]:
    counter, records = Counter(), []
    base, guard, grant = configuration(live, grant_path)
    stopped = None
    for case in CASES:
        for model in MODELS:
            try:
                # Only this fixed, manually authorized comparison can override
                # the operational model lock; there is no arbitrary model flag.
                settings = {key: value for key, value in base.settings.items() if key != "model_lock"}
                records.extend(
                    execute_case(
                        replace(base, model=model, caps=CAPS, settings=settings),
                        case,
                        counter,
                        mock=not live,
                        grant=grant,
                    )
                )
            except Exception as error:
                stopped = getattr(error, "code", "PROBE_CHECK_FAILED")
                break
        if stopped:
            break
    if live and stopped is None:
        try:
            guard.finish_batch(grant.batch_id, grant.authorization_id)
        except Exception:
            stopped = "BATCH_FINISH_FAILED"
    return dict(
        schema="k3-equivalence-check-v1",
        at=get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        mode="live" if live else "mock",
        model_calls=counter.attempts if live else 0,
        mock_requests=0 if live else counter.attempts,
        physical_attempt_limit=MAX_ATTEMPTS,
        passed=stopped is None and len(records) == MAX_ATTEMPTS,
        stopped_code=stopped,
        records=records,
        automatic_next_batch=False,
        limitations=["capability checks do not establish blind quality equivalence", "256k capacity is not measured"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "live"), default="mock")
    parser.add_argument("--grant", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = None
    try:
        if args.output.exists() or not args.output.parent.is_dir():
            raise ProbeRejected("输出须为已有目录里的新文件")
        result = run(live=args.mode == "live", grant_path=args.grant)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        print(
            json.dumps({key: result[key] for key in ("passed", "mode", "model_calls", "mock_requests", "stopped_code")})
        )
        return 0 if result["passed"] else 2
    except Exception as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "code": getattr(error, "code", "PROBE_CONFIGURATION_ERROR"),
                    "model_calls": result["model_calls"] if result is not None else 0,
                }
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

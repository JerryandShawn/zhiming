"""Quota-protected Kimi Code probes. Results contain counts, never answer bodies."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from mingjing_core.models.errors import ModelQuotaExhausted, ModelUnavailable  # noqa: E402
from mingjing_core.models.port import ChatMessage  # noqa: E402
from mingjing_core.models.quota_runtime import (  # noqa: E402
    CentralLocation,
    call_scope,
    current_scope,
)
from mingjing_core.models.quota_types import GuardRejected  # noqa: E402
from mingjing_core.models.registry import ModelRegistry  # noqa: E402
from mingjing_core.timekit.clock import get_clock  # noqa: E402
from tools.manual_grant import load_manual_grant  # noqa: E402
from tools.model_probe_cases import Probe, cases  # noqa: E402

PROBE_CAPS = {
    "tools": True,
    "vision": True,
    "tool_choice": ["auto", "none", "required", "named"],
    "include_usage": True,
    "reasoning_field": "reasoning_content",
    "reasoning_replay": True,
    "schema_dialect": "anthropic",
    "probe_raw_schema": True,
    "sampling_fixed": True,
}


def _run(handle: Any, probe: Probe) -> dict[str, Any]:
    adapter = replace(handle, protocol=probe.protocol, caps=PROBE_CAPS, role="evaluation").adapter(max_retries=0)
    started, first = time.monotonic(), None
    text, calls, usage, reasoning = "", [], {}, 0
    error, status, quota = None, None, False
    try:
        with call_scope(replace(current_scope(), lane="probe", scenario_id=probe.name)):
            events = adapter.stream(
                probe.messages,
                tools=probe.tools,
                tool_choice=probe.choice,
                max_output=probe.max_output,
                role="evaluation",
            )
            for event in events:
                text, calls, usage, reasoning, first = _observe(event, text, calls, usage, reasoning, first, started)
    except ModelQuotaExhausted as exc:
        error, status, quota = exc.code, exc.provider_http_status, True
    except ModelUnavailable as exc:
        error, status, quota = (
            exc.code,
            exc.provider_http_status,
            exc.global_stop or isinstance(exc, GuardRejected),
        )
    except Exception:
        error = "MODEL_PROTOCOL_ERROR"
    chinese = sum("\u4e00" <= char <= "\u9fff" for char in text)
    passed = error is None and (
        len(calls) >= 2
        if probe.name == "parallel_tools"
        else bool(calls)
        if probe.tools and probe.choice != "none"
        else chinese >= 2000 and "【合成完毕】" in text
        if probe.name == "chinese_long_output"
        else bool(usage)
        if probe.name == "include_usage"
        else not calls
        if probe.name == "tool_choice_none"
        else bool(text)
    )
    return {
        "model": handle.model,
        "probe": probe.name,
        "protocol": probe.protocol,
        "passed": passed,
        "http_status": status,
        "error_code": error,
        "quota": quota,
        "calls": adapter.request_count,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "first_event_seconds": round(first, 3) if first is not None else None,
        "text_chars": len(text),
        "chinese_chars": chinese,
        "tool_count": len(calls),
        "reasoning_chars": reasoning,
        "usage": usage,
    }


def _observe(
    event: Any,
    text: str,
    calls: list[Any],
    usage: dict[str, Any],
    reasoning: int,
    first: float | None,
    started: float,
) -> tuple[str, list[Any], dict[str, Any], int, float | None]:
    if event.type in {"text", "tool_call", "reasoning"} and first is None:
        first = time.monotonic() - started
    if event.type == "text":
        text += event.data
    elif event.type == "tool_call":
        calls.append(event.data)
    elif event.type == "usage":
        usage.update(event.data)
    elif event.type == "reasoning":
        reasoning += len(event.data)
    elif event.type == "error":
        raise event.data
    return text, calls, usage, reasoning, first


def _roundtrip(handle: Any, replay: bool) -> dict[str, Any]:
    from tools.model_probe_cases import cases

    caps = {**PROBE_CAPS, "reasoning_replay": replay}
    adapter = replace(handle, caps=caps, role="evaluation").adapter(max_retries=0)
    started = time.monotonic()
    error, status, quota, passed = None, None, False, False
    try:
        if not replay:
            raise GuardRejected("manual_start_required")
        initial = cases()[1]
        with call_scope(replace(current_scope(), lane="probe", scenario_id="reasoning_replay_true")):
            first = adapter.complete(
                initial.messages,
                tools=initial.tools,
                max_output=1800,
                role="evaluation",
            )
            if len(first.tool_calls) != 1:
                raise ModelUnavailable()
            second = adapter.complete(
                [
                    *initial.messages,
                    first.as_chat(tool_cycle="probe"),
                    ChatMessage(
                        "tool",
                        "合成探针",
                        tool_call_id=first.tool_calls[0].id,
                        tool_cycle="probe",
                    ),
                ],
                max_output=800,
                role="evaluation",
            )
        passed = bool(second.text)
    except ModelQuotaExhausted as exc:
        error, status, quota = exc.code, exc.provider_http_status, True
    except ModelUnavailable as exc:
        error, status, quota = (
            exc.code,
            exc.provider_http_status,
            exc.global_stop or isinstance(exc, GuardRejected),
        )
    except Exception:
        error = "MODEL_PROTOCOL_ERROR"
    return {
        "model": handle.model,
        "probe": "reasoning_replay_" + str(replay).lower(),
        "protocol": handle.protocol,
        "passed": passed,
        "http_status": status,
        "error_code": error,
        "quota": quota,
        "calls": adapter.request_count,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def publish(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    report["total_calls"] = sum(row["calls"] for row in report["results"])
    output.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Kimi Code 模型能力探针",
        "",
        f"状态：{report['status']}；实际调用 {report['total_calls']} 次。",
        "服务器配置未读取（夜间禁止）；仅本机用户环境的会员端点。客户端标识 MingjingCore/3.0。",
        "未提供其他供应商密钥，未探测。失败/未执行项不得解释为已支持。",
        "",
        "| 模型 | 探针/协议 | 通过 | 调用 | 安全错误 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["results"]:
        lines.append(
            f"| {row['model']} | {row['probe']} / {row['protocol']} | {row['passed']} | "
            f"{row['calls']} | {row['error_code'] or '—'} |"
        )
    lines.extend(
        [
            "",
            "官方参考（2026-10-17 核查）：",
            "- https://www.kimi.com/help/kimi-code/models （模型 ID、兼容端点与 k3 约两倍额度说明）",
            "- https://www.kimi.com/code/docs/en/kimi-code/error-reference.html （会员/额度错误）",
            "- https://platform.claude.com/docs/en/build-with-claude/streaming （Messages SSE）",
            "- https://api-docs.deepseek.com/guides/thinking_mode/ （reasoning 回传按能力配置；未实测）",
            "",
            "额度错误立即结束整个夜间真实调用，未重试，未访问兄弟模型。",
        ]
    )
    output.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_caps(report: dict[str, Any], path: Path) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for model in ("k3", "k3-256k"):
        rows = {row["probe"]: row for row in report["results"] if row["model"] == model}
        if not rows:
            continue

        def succeeded(name: str, observed: dict[str, Any] = rows) -> bool:
            return bool(observed.get(name, {}).get("passed", False))

        entries = [entry for entry in data["models"].values() if entry.get("model") == model]
        for entry in entries:
            _update_entry(entry, report, succeeded)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _update_entry(entry: dict[str, Any], report: dict[str, Any], succeeded: Any) -> None:
    entry["caps"].update(
        status="partial" if report["status"] != "complete" else "probed",
        tools=succeeded("single_tool"),
        parallel_tools=succeeded("parallel_tools"),
        vision=succeeded("vision"),
        tool_choice=[choice for choice in ("auto", "required") if succeeded("tool_choice_" + choice)],
        reasoning_replay=True,
        sampling_fixed=True,
        probe_report="docs/v4/" + report["report_name"],
    )


def _handles(registry: ModelRegistry) -> list[Any]:
    # Explicit comparison is the only place where D2's default model lock is removed.
    base = registry.resolve("primary")[0]
    endpoint = urlsplit(base.base_url)
    if (
        base.provider != "kimi_code"
        or endpoint.scheme != "https"
        or endpoint.hostname != "api.kimi.com"
        or endpoint.path.rstrip("/") != "/coding/v1"
    ):
        raise SystemExit("Probe preflight: unapproved membership endpoint")
    settings = {key: value for key, value in base.settings.items() if key != "model_lock"}
    return [replace(base, model=model, settings=settings, role="evaluation") for model in ("k3", "k3-256k")]


def _jobs(handle: Any, approved: tuple[str, ...]) -> list[tuple[str, Any]]:
    available = {probe.name: (lambda p=probe: _run(handle, p)) for probe in cases()}
    available["reasoning_replay_true"] = lambda: _roundtrip(handle, True)
    if not set(approved).issubset(available):
        raise SystemExit("Probe preflight: unknown or policy-disabled scenario")
    return [(name, available[name]) for name in approved]


def _execute(handles: list[Any], grant: Any, report: dict[str, Any], args: Any) -> int:
    for handle in handles:
        for name, run in _jobs(handle, grant.scenario_ids):
            with call_scope(grant.scope(name)):
                row = run()
            row["batch"] = 1
            report["results"].append(row)
            if row["quota"]:
                report["status"] = "quota_stopped"
                args.stop_file.parent.mkdir(parents=True, exist_ok=True)
                args.stop_file.write_text(
                    json.dumps(
                        {
                            "reason": row["error_code"],
                            "role": "probe",
                            "model": handle.model,
                        }
                    ),
                    encoding="utf-8",
                )
            publish(report, args.output)
            print(
                f"{handle.model} {row['probe']}: {row['passed']}; calls={row['calls']}",
                flush=True,
            )
            if row["quota"]:
                return 2
    CentralLocation.from_environment().guard().finish_batch(grant.batch_id, grant.authorization_id)
    report["status"] = "complete"
    publish(report, args.output)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    day = get_clock().now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
    parser.add_argument("--output", type=Path, default=ROOT / f"docs/v4/model-probe-{day}")
    parser.add_argument("--models", default="k3,k3-256k")
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--manual-grant", type=Path)
    parser.add_argument("--update-caps", action="store_true")
    args = parser.parse_args()
    if args.models != "k3,k3-256k" or args.stop_file.exists():
        raise SystemExit("Night policy: only k3/k3-256k and no calls after a quota stop")
    if args.manual_grant is None:
        raise SystemExit("Probe preflight: an existing local-terminal manual grant is required")
    grant = load_manual_grant(args.manual_grant, "PROBE", [])
    registry = ModelRegistry()
    handles = _handles(registry)
    _jobs(handles[0], grant.scenario_ids)  # validate the whole batch before any physical call
    report = {
        "date": get_clock().now().isoformat(),
        "status": "running",
        "synthetic_only": True,
        "results": [],
        "batch_size": 10,
        "report_name": args.output.name + ".json",
    }
    result = _execute(handles, grant, report, args)
    if args.update_caps:
        update_caps(report, registry.path)
    print(f"Actual probe calls: {report['total_calls']}")
    return result


if __name__ == "__main__":
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    raise SystemExit(main())

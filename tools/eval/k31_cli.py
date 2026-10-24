"""Claude operator entry: explicit isolated control initialization or R16 checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.agent.k3_loader import load_k3_counter
from mingjing_core.models.quota_delegated import resume_delegated
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_runtime import CentralLocation
from mingjing_core.models.registry import ModelRegistry
from tools.eval.k31_connect import run_connection
from tools.eval.k31_contract import MODEL, SCENARIOS
from tools.eval.k31_control import K31Control
from tools.eval.r11_gate import ROOT, candidate_r11
from tools.manual_grant_io import write_private_receipt
from tools.probe_equivalence_control import ProbeControlError


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("init-control", "status", "resume-ready", "connect"))
    result.add_argument("--control-schema", required=True)
    result.add_argument("--scripted-gate", type=Path)
    result.add_argument("--candidate")
    result.add_argument("--tokenizer-dir", type=Path)
    result.add_argument("--output", type=Path)
    return result


def execute(args) -> int:
    os.environ.update(
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        OTEL_SDK_DISABLED="true",
        FEISHU_ENABLED="false",
        CORE_FEISHU_ENABLED="false",
    )
    control = K31Control(os.environ.get("PROBE_CONTROL_DSN", ""), args.control_schema)
    if args.action == "init-control":
        control.initialize()
        print(json.dumps({"initialized": True, "model_calls": 0}))
        return 0
    guard = CentralLocation.from_environment().guard()
    if args.action == "status":
        state = guard.status()
        print(json.dumps({key: state[key] for key in ("stop_kind", "resume_at", "window", "in_flight")}, default=str))
        return 0
    if args.scripted_gate is None or not args.candidate:
        raise ProbeControlError("需要同源候选及R11脚本门")
    approval = candidate_r11(args.scripted_gate, args.candidate, guard.clock.now())
    if args.action == "resume-ready":
        print(json.dumps({"resumed": resume_delegated(guard, approval), "model_calls": 0}))
        return 0
    if (
        args.tokenizer_dir is None
        or not args.tokenizer_dir.is_absolute()
        or args.output is None
        or not args.output.is_absolute()
        or args.output.exists()
        or not args.output.parent.is_dir()
        or not args.output.resolve().is_relative_to(ROOT / "private")
    ):
        raise ProbeControlError("需要固定分词器路径和private内新的输出文件")
    registry = ModelRegistry(ROOT / "config/models.first-release.yaml")
    meter = K3EstimatedMeter(load_k3_counter(args.tokenizer_dir), model=MODEL)
    session = DelegatedSession(guard, approval, phase="k31-connect", scenario_ids=SCENARIOS)
    result = run_connection(registry, session, control, meter)
    write_private_receipt(args.output, result)
    print(json.dumps({key: result[key] for key in ("complete", "model_calls", "stop_kind", "resume_at")}))
    return 0 if result["complete"] else 2


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return execute(args)
    except Exception as error:
        print(json.dumps({"ok": False, "code": getattr(error, "code", "K31_OPERATION_REJECTED")}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

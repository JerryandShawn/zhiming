"""Create one short-lived central grant after exact text entered on a local terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import CentralLocation
from mingjing_core.models.quota_types import GuardConfigurationError, GuardRejected, identifier

SUITES = {"E1": "E1", "E2": "E2", "PROBE": "探针"}


class ManualStartRejected(ValueError):
    code = "MANUAL_START_REQUIRED"


def confirmation_text(suite: str, batch_number: int) -> str:
    if suite not in SUITES or type(batch_number) is not int or not 1 <= batch_number <= 10000:
        raise ManualStartRejected("批次或评测类型无效")
    return f"开始 {SUITES[suite]} 第 {batch_number} 批"


def confirm_local(suite: str, batch_number: int) -> None:
    expected = confirmation_text(suite, batch_number)
    try:
        local = sys.stdin.isatty() and os.isatty(sys.stdin.fileno())
    except (AttributeError, OSError, ValueError):
        local = False
    if not local:
        raise ManualStartRejected("只能由用户在线在本机终端输入确认，管道或参数不能代替")
    print(f"本次只授权当前批；不会自动开始下一批。请完整输入：{expected}", flush=True)
    actual = sys.stdin.readline(128).rstrip("\r\n")
    if actual != expected:
        raise ManualStartRejected("确认文字不匹配，没有创建批次授权")


def grant_batch(guard: QuotaGuard, suite: str, batch_number: int, scenarios: list[str]) -> dict[str, Any]:
    confirmation_text(suite, batch_number)
    if not 1 <= len(scenarios) <= 10 or len(set(scenarios)) != len(scenarios):
        raise ManualStartRejected("每批必须为一至十个不同场景")
    for scenario in scenarios:
        identifier(scenario)
    stamp = guard.clock.now()
    batch = f"manual-{suite.lower()}-{batch_number}-" + uuid.uuid4().hex
    authorization = "terminal-" + uuid.uuid4().hex
    expires = stamp + timedelta(minutes=15)
    guard.begin_batch(batch_id=batch, authorization_id=authorization, scenario_ids=scenarios, expires_at=expires)
    return {
        "schema": "member-manual-start-v1",
        "suite": suite,
        "batch_number": batch_number,
        "batch_id": batch,
        "authorization_id": authorization,
        "scenario_ids": scenarios,
        "expires_at": expires.isoformat(),
        "automatic_next_batch": False,
        "model_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=tuple(SUITES), required=True)
    parser.add_argument("--batch-number", type=int, required=True)
    parser.add_argument("--scenario", action="append", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.receipt.exists() or not args.receipt.parent.is_dir():
            raise ManualStartRejected("收据必须使用现有目录下的新文件")
        confirm_local(args.suite, args.batch_number)
        guard = CentralLocation.from_environment().guard()
        receipt = grant_batch(guard, args.suite, args.batch_number, args.scenario)
        with args.receipt.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, ensure_ascii=False, sort_keys=True, indent=2)
        print(json.dumps({"ok": True, "receipt": str(args.receipt), "model_calls": 0, "automatic_next_batch": False}))
        return 0
    except (ManualStartRejected, GuardConfigurationError, GuardRejected) as error:
        print(json.dumps({"ok": False, "code": error.code, "model_calls": 0, "automatic_next_batch": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

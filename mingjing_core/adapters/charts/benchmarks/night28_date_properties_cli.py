"""Standalone offline property runner with fingerprints and Beijing timestamps."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import timedelta, timezone
from pathlib import Path
from time import perf_counter

from ....timekit.clock import get_clock
from ..p8_worker import source_hashes
from ..time_basis_zones import load_zone
from .handoff_offline import offline_runtime
from .night28_date_cases import SEED
from .night28_date_properties import run_random


def _metadata(suite: str) -> dict:
    names = (
        "night28_date_cases.py",
        "night28_date_properties.py",
        "night28_date_properties_cli.py",
        "night28_property_common.py",
        "night28_window_properties.py",
        "night28_ziwei_reference.py",
    )
    parent = Path(__file__).parent
    digests = {
        name: hashlib.sha256(
            (parent / name).read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for name in names
    }
    return {
        "version": "p8-night28-date-properties-v1",
        "seed": SEED,
        "suite": suite,
        "generated_at_beijing": get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(),
        "source_sha256": source_hashes(),
        "benchmark_sha256": digests,
        "timezone_source": load_zone("Asia/Shanghai")[1],
        "model_calls": 0,
        "writes_to_profiles": 0,
    }


def _write(report: dict, output: Path) -> int:
    report["limits"] = [
        "1000去重随机日期不等于1000名真人或预测准确率。",
        "闰月/节界共用安装库；日差时干为独立算式，但共用经库核对的甲子锚，不声称独立历史天文真值。",
        "UTC/Tokyo环境变形不等于已在另一操作系统运行；不更改宿主系统时区。",
    ]
    failures = sum(
        section["failure_count"]
        for section in report.get("calendar", {}).values()
        if isinstance(section, dict) and "failure_count" in section
    )
    failures += report.get("annual", {}).get("failure_count", 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "suite": report["suite"],
                "failures": failures,
                "elapsed_seconds": report["elapsed_seconds"],
            }
        )
    )
    return int(bool(failures))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--suite", choices=["random", "annual", "all"], default="all")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    platform.uname()
    report, started = _metadata(args.suite), perf_counter()
    with offline_runtime():
        if args.suite in ("random", "all"):
            report["calendar"] = run_random(args.count)
        if args.suite in ("annual", "all"):
            from .night28_window_properties import run_annual

            report["annual"] = run_annual()
    report["elapsed_seconds"] = perf_counter() - started
    raise SystemExit(_write(report, args.output))


if __name__ == "__main__":
    main()

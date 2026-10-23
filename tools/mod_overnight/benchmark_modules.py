"""Reproducible offline performance observations; never measures prediction quality or wire QPS."""

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402


def _measure(name: str, operation: Callable[[], object], count: int, repeats: int) -> dict:
    operation()
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        operation()
        samples.append(perf_counter() - started)
    tracemalloc.start()
    try:
        operation()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    median = statistics.median(samples)
    return {
        "case": name,
        "items_per_run": count,
        "repeats": repeats,
        "warmup_runs": 1,
        "seconds": samples,
        "median_seconds": median,
        "p95_nearest_rank_seconds": sorted(samples)[math.ceil(repeats * 0.95) - 1],
        "max_seconds": max(samples),
        "median_ms_per_item": median * 1000 / count,
        "items_per_cpu_wall_second": count / median,
        "separate_tracemalloc_run_peak_bytes": peak,
    }


def _source_hashes() -> dict[str, str]:
    tracked = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=A", "b9a89b6f84f7bebb640de080548010859aae630c"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in sorted(set(tracked + untracked))
        if name.endswith(".py")
    }


def run(repeats: int = 5, *, selected: Sequence[str] | None = None) -> dict:
    from tools.mod_overnight.benchmark_cards import cases as card_cases
    from tools.mod_overnight.benchmark_organize import cases as organize_cases
    from tools.mod_overnight.benchmark_validation_followups import cases as rule_cases

    if type(repeats) is not int or not 3 <= repeats <= 20:
        raise ValueError("性能重复次数须为3至20")
    jobs = organize_cases() + rule_cases() + card_cases()
    if selected is not None:
        names = set(selected)
        if not names or not names <= {name for name, _, _ in jobs}:
            raise ValueError("未知性能场景")
        jobs = [job for job in jobs if job[0] in names]
    observations = [_measure(name, operation, count, repeats) for name, operation, count in jobs]
    return {
        "kind": "offline_synthetic_cpu_observation",
        "observed_at_utc": SystemClock().now().isoformat(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "runtime": {
            "python": platform.python_version(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
        },
        "observations": observations,
        "source_sha256": _source_hashes(),
        "limitations": [
            "Keyword mode; no ONNX or real embedding measurement",
            "6000 messages repeat the frozen corpus for scale only, not a new accuracy set",
            "CardKit uses FrozenClock and fake transport; throughput is not real network QPS",
            "p95 of a small sample is descriptive, not a confidence interval",
            "tracemalloc is one separate run, not process RSS or native model memory",
            "No real model, server, database or Feishu access",
        ],
    }


def write_report(report: dict, destination: Path) -> None:
    resolved = destination.resolve()
    if not resolved.is_relative_to(ROOT) or resolved.suffix != ".json":
        raise ValueError("性能报告只能写入模块工作目录的JSON文件")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--case", action="append", dest="selected")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.repeats, selected=args.selected)
    write_report(report, args.output)
    for result in report["observations"]:
        print(
            result["case"],
            "median_s=",
            round(result["median_seconds"], 6),
            "max_s=",
            round(result["max_seconds"], 6),
            "items=",
            result["items_per_run"],
        )
    small = next((item for item in report["observations"] if item["case"] == "organize_keyword_600"), None)
    if small is not None and small["max_seconds"] >= 60:
        raise SystemExit("600-message organization exceeded 60 seconds")


if __name__ == "__main__":
    main()

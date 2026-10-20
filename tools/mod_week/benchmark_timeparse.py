"""U4 CPU/allocation observations with explicit Beijing reference; no private text is emitted."""

import argparse
import hashlib
import json
import statistics
import sys
import tracemalloc
from datetime import datetime
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402

REF = datetime(2026, 10, 17, 9, tzinfo=ZoneInfo("Asia/Shanghai"))
SIMPLE = ("明天", "下周三", "三天后", "两周内", "下午三点", "下周末", "月底", "下季度")
CALENDAR = ("2026年冬至那天", "2026年国庆之后第一个工作日", "2026年农历八月十五", "2026年春节期间")


def workload(expressions: tuple[str, ...], count: int) -> int:
    from mingjing_core.timeparse.parser import parse_time_range

    completed = 0
    for index in range(count):
        result = parse_time_range(expressions[index % len(expressions)], REF)
        assert result.original_text == expressions[index % len(expressions)]
        assert result.start is None or result.start.utcoffset() is not None
        if result.start is None:
            assert result.needs_clarification
        json.dumps(result.as_dict(), ensure_ascii=False)
        completed += 1
    return completed


def measure(name: str, expressions: tuple[str, ...], count: int, repeats: int) -> dict:
    assert workload(expressions, count) == count
    samples = []
    for _ in range(repeats):
        started = perf_counter()
        assert workload(expressions, count) == count
        samples.append(perf_counter() - started)
    tracemalloc.start()
    try:
        workload(expressions, count)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "case": name,
        "count_per_run": count,
        "warmup": 1,
        "observations": repeats,
        "seconds": samples,
        "median_seconds": statistics.median(samples),
        "max_seconds": max(samples),
        "separate_tracemalloc_peak_bytes": peak,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.count <= 20_000 or not 3 <= args.repeats <= 10:
        raise SystemExit("观测次数或样本数量无效")
    destination = args.output.resolve()
    if not destination.is_relative_to(ROOT) or destination.suffix != ".json":
        raise SystemExit("报告只能写入模块工作目录JSON文件")
    cases = [
        measure("u4_natural", SIMPLE, args.count, args.repeats),
        measure("u4_p2_calendar", CALENDAR, args.count, args.repeats),
    ]
    report = {
        "observed_at": SystemClock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "reference_at": REF.isoformat(),
        "kind": "synthetic_local_only",
        "cases": cases,
        "source_sha256": {
            str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((ROOT / "mingjing_core/timeparse").glob("*.py"))
        },
        "limitations": [
            "CPU wall time; repeated expressions may benefit from pinned calendar-library caches",
            "tracemalloc is Python allocation, not process RSS; no model/network/database",
        ],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in cases:
        print(result["case"], "median_s", round(result["median_seconds"], 6), "count", args.count)


if __name__ == "__main__":
    main()

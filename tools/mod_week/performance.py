"""Small reusable benchmark recorder; observations are separate from correctness tests."""

import hashlib
import json
import statistics
import tracemalloc
from collections.abc import Callable, Iterable
from pathlib import Path
from time import perf_counter
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock

ROOT = Path(__file__).resolve().parents[2]


def measure(name: str, operation: Callable[[], int], *, repeats: int = 5) -> dict:
    if not name or not 3 <= repeats <= 10:
        raise ValueError("性能观测配置无效")
    completed = operation()
    if type(completed) is not int or completed < 1:
        raise ValueError("性能操作必须报告正整数工作量")
    observations = []
    for _ in range(repeats):
        started = perf_counter()
        if operation() != completed:
            raise ValueError("性能工作量不稳定")
        observations.append(perf_counter() - started)
    if tracemalloc.is_tracing():
        raise ValueError("性能分配观测不能嵌套")
    tracemalloc.start()
    try:
        if operation() != completed:
            raise ValueError("性能工作量不稳定")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {
        "name": name,
        "units_per_run": completed,
        "warmup": 1,
        "observations": repeats,
        "seconds": observations,
        "median_seconds": statistics.median(observations),
        "max_seconds": max(observations),
        "separate_tracemalloc_peak_bytes": peak,
    }


def write_report(destination: Path, cases: list[dict], sources: Iterable[Path], *, clock: Clock) -> dict:
    target = destination.resolve()
    if not target.is_relative_to(ROOT) or target.suffix != ".json":
        raise ValueError("性能报告只能写本工作目录JSON")
    source_paths = tuple(path.resolve() for path in sources)
    if any(not path.is_relative_to(ROOT) for path in source_paths):
        raise ValueError("性能来源必须在本工作目录")
    stamp = clock.now()
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("性能观察时刻需要时区")
    report = {
        "observed_at": stamp.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "kind": "synthetic_local_only",
        "cases": cases,
        "source_sha256": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source_paths)
        },
        "limitations": [
            "CPU wall time; caches may help repeated workloads",
            "tracemalloc measures Python allocations, not process RSS",
            "No network, model, database or production end-to-end inference",
        ],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report

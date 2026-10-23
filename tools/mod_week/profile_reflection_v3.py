"""Deterministic cProfile observations of frozen, explicitly synthetic reflection workloads."""

import argparse
import cProfile
import hashlib
import json
import pstats
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tools.mod_week.benchmark_reflection_v3 import FIXTURE, full_workload, invalidation_workload  # noqa: E402


def source_hashes() -> dict[str, str]:
    directories = ("mingjing_core/application/reflection_v3", "mingjing_core/memory2", "mingjing_core/timeparse")
    paths = [file for directory in directories for file in (ROOT / directory).glob("*.py")]
    paths.extend(
        ROOT / name
        for name in (
            "tools/mod_week/benchmark_reflection_v3.py",
            "tools/mod_week/profile_reflection_v3.py",
            "mingjing_core/memory/slots.py",
            "mingjing_core/memory/policy.py",
            "mingjing_core/timekit/clock.py",
            "mingjing_core/scheduling/recurrence_contracts.py",
            "mingjing_core/scheduling/recurrence_wall.py",
        )
    )
    paths.append(FIXTURE)
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def normalized_filename(filename: str) -> str:
    if filename.startswith(("<", "~")):
        return filename
    path = Path(filename)
    if path.is_absolute() and path.is_relative_to(ROOT):
        return path.relative_to(ROOT).as_posix()
    if path.is_absolute():
        # Standard-library locations identify functions, never profile arguments or local variables.
        components = path.parts
        lower = tuple(part.lower() for part in components)
        if "lib" in lower:
            return "stdlib/" + "/".join(components[lower.index("lib") + 1 :])
        return "external/" + path.name
    return filename.replace("\\", "/")


def function_id(key: tuple[str, int, str]) -> str:
    return f"{normalized_filename(key[0])}:{key[1]}:{key[2]}"


def category(filename: str) -> str:
    if "application/reflection_v3/" in filename:
        return "reflection_v3"
    if "mingjing_core/memory2/" in filename:
        return "frozen_memory2"
    if "mingjing_core/timeparse/" in filename:
        return "frozen_timeparse"
    if "tools/mod_week/benchmark_reflection_v3.py" in filename:
        return "synthetic_input_construction_and_assertions"
    if "dataclasses.py" in filename:
        return "stdlib_dataclasses"
    if filename.startswith("stdlib/re/"):
        return "stdlib_regex_helpers"
    if filename.startswith("stdlib/"):
        return "other_standard_library"
    return "other_or_builtin"


def stats_rows(stats: pstats.Stats) -> tuple[list[dict[str, Any]], dict[str, dict[str, float | int]]]:
    rows = []
    groups: dict[str, dict[str, float | int]] = defaultdict(lambda: {"total_calls": 0, "self_seconds": 0.0})
    for key, (primitive, total, own, cumulative, callers) in stats.stats.items():
        filename = normalized_filename(key[0])
        caller_rows = [
            {
                "function_id": function_id(caller),
                "primitive_calls": value[0],
                "total_calls": value[1],
                "self_seconds": value[2],
                "cumulative_seconds": value[3],
            }
            for caller, value in callers.items()
        ]
        row = {
            "function_id": function_id(key),
            "file": filename,
            "line": key[1],
            "name": key[2],
            "primitive_calls": primitive,
            "total_calls": total,
            "recursive_calls": total - primitive,
            "self_seconds": own,
            "cumulative_seconds": cumulative,
            "self_seconds_per_call": own / total if total else 0.0,
            "cumulative_seconds_per_primitive_call": cumulative / primitive if primitive else 0.0,
            "callers": sorted(caller_rows, key=lambda item: (-item["cumulative_seconds"], item["function_id"])),
        }
        rows.append(row)
        group = groups[category(filename)]
        group["total_calls"] += total
        group["self_seconds"] += own
    return sorted(rows, key=lambda row: row["function_id"]), dict(groups)


def profile_case(name: str, operation: Callable[[], int], expected_units: int) -> dict[str, Any]:
    if operation() != expected_units:
        raise ValueError("profile_workload_warmup_units_changed")
    baselines = []
    for _ in range(3):
        started = perf_counter()
        if operation() != expected_units:
            raise ValueError("profile_workload_baseline_units_changed")
        baselines.append(perf_counter() - started)
    profiler = cProfile.Profile()
    started = perf_counter()
    completed = profiler.runcall(operation)
    profiled_wall = perf_counter() - started
    if completed != expected_units:
        raise ValueError("profile_workload_units_changed")
    stats = pstats.Stats(profiler)
    rows, groups = stats_rows(stats)
    if not rows or any(row["total_calls"] < row["primitive_calls"] or row["self_seconds"] < 0 for row in rows):
        raise ValueError("profile_function_statistics_invalid")
    if (
        sum(row["total_calls"] for row in rows) != stats.total_calls
        or sum(row["primitive_calls"] for row in rows) != stats.prim_calls
        or abs(sum(row["self_seconds"] for row in rows) - stats.total_tt) > 1e-8
    ):
        raise ValueError("profile_statistics_totals_do_not_match")
    median = statistics.median(baselines)
    return {
        "name": name,
        "units_per_run": expected_units,
        "warmup_runs": 1,
        "unprofiled_observations": 3,
        "unprofiled_wall_seconds": baselines,
        "unprofiled_median_seconds": median,
        "profiled_wall_seconds": profiled_wall,
        "observed_profiled_to_unprofiled_ratio": profiled_wall / median,
        "primitive_calls": stats.prim_calls,
        "total_calls": stats.total_calls,
        "summed_function_self_seconds": stats.total_tt,
        "function_count": len(rows),
        "top_by_cumulative": sorted(rows, key=lambda row: (-row["cumulative_seconds"], row["function_id"]))[:20],
        "top_by_self": sorted(rows, key=lambda row: (-row["self_seconds"], row["function_id"]))[:20],
        "exclusive_self_by_category": groups,
        "all_functions": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT) or output.suffix != ".json":
        raise ValueError("profile_output_must_be_a_new_local_json_file")
    fixture, before = FIXTURE.read_bytes(), source_hashes()
    if json.loads(fixture).get("synthetic") is not True:
        raise ValueError("profile_requires_explicitly_synthetic_fixture")
    cases = []
    for name, operation, units in (
        ("full_enqueue_work_aboutme_100", full_workload, 100),
        ("revoked_epoch_invalidation_only_1000", invalidation_workload, 1000),
    ):
        cases.append(profile_case(name, lambda fn=operation: fn(fixture), units))
        print(name, "profile complete", flush=True)
    after = source_hashes()
    if before != after:
        raise ValueError("profile_source_changed_during_observation")
    report = {
        "observed_at": SystemClock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "kind": "synthetic_local_instrumented_cprofile",
        "runtime": {"python": sys.version, "implementation": sys.implementation.name, "timer": "cProfile default"},
        "source_sha256": before,
        "source_hashes_unchanged": True,
        "cases": cases,
        "limitations": [
            "cProfile instruments calls; this is not statistical sampling and it perturbs short-call costs",
            "Ratios compare one instrumented run with three warm unprofiled observations; not causal overhead",
            "Cumulative times overlap through nesting; only exclusive self category totals are additive",
            "Input construction, frozen guards, full workload and assertions are inside the profiled operation",
            "Imports, fixture byte read, source hashing and report write are excluded",
            "Host scheduling, concurrent local work and warm caches affect results; these are not production timings",
            "No production data, model, network, database, queue, notification or application optimization",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("profile evidence written", flush=True)


if __name__ == "__main__":
    main()

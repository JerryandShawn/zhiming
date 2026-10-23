"""Bounded local timings of the synthetic handoff; never an HTTP/model SLA."""

from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
from pathlib import Path
from time import perf_counter

from .handoff_build import build_preview
from .handoff_refs import digest
from .handoff_validate import validate_preview


def summarize(values: list[float]) -> dict:
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("performance_finite_nonnegative_samples_required")
    ordered = sorted(values)
    return {
        "n": len(values),
        "minimum_seconds": round(ordered[0], 6),
        "median_seconds": round(statistics.median(values), 6),
        "p95_nearest_rank_seconds": round(
            ordered[math.ceil(0.95 * len(values)) - 1], 6
        ),
        "maximum_seconds": round(ordered[-1], 6),
    }


def measure_once(system: str, chart_python: str) -> dict:
    started = perf_counter()
    preview = build_preview(system, chart_python)
    computed = perf_counter()
    validate_preview(preview, verify_runtime_sources=True)
    validated = perf_counter()
    encoded = json.dumps(preview, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    serialized = perf_counter()
    return {
        "compute_seconds": computed - started,
        "validation_seconds": validated - computed,
        "serialization_seconds": serialized - validated,
        "total_seconds": serialized - started,
        "envelope_sha256": digest(preview),
        "pretty_json_utf8_bytes": len(encoded.encode("utf8")),
        "rule_hits": len(preview["view"]["rules"]),
        "documents": len(preview["documents"]),
        "model_calls": preview["effects"]["model_calls"],
        "writes": preview["effects"]["writes"],
    }


def measure_system(system: str, chart_python: str, repeats: int, warmups: int) -> dict:
    if not 1 <= repeats <= 20 or not 0 <= warmups <= 2:
        raise ValueError("performance_bounded_repeat_count_required")
    observed = [measure_once(system, chart_python) for _ in range(warmups + repeats)]
    if any(row["model_calls"] != 0 or row["writes"] != 0 for row in observed):
        raise ValueError("performance_readonly_effects_required")
    measured = observed[warmups:]
    return {
        "system": system,
        "warmups_excluded": warmups,
        "repeats": repeats,
        "fresh_worker_per_calculation": True,
        "result_envelope_hash_stable": len({r["envelope_sha256"] for r in observed})
        == 1,
        "output_sizes_stable": len({r["pretty_json_utf8_bytes"] for r in observed})
        == 1,
        "summary": {
            key: summarize([row[key] for row in measured])
            for key in (
                "compute_seconds",
                "validation_seconds",
                "serialization_seconds",
                "total_seconds",
            )
        },
        "observations": measured,
        "model_calls": 0,
        "writes": 0,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# 夜间合成接线预览性能观测（2026-10-19）",
        "",
        "固定阿远、固定2026-10-19目标日；每次重新启动隔离排盘工作进程。",
        "以下含计算、Schema/语义校验与内存JSON序列化，不含磁盘写出、HTTP、模型或并发负载；不是线上SLA。",
        "预热仅使父进程导入/OS缓存趋稳，每次子进程仍重新启动；样本量小，P95使用nearest-rank，不推断总体尾延迟。",
        "",
        "| 系统 | 排除预热 | 样本数 | 计算中位秒 | 总中位秒 | 总P95秒 | 总最大秒 | 输出hash稳定 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in report["systems"]:
        total, compute = (
            row["summary"]["total_seconds"],
            row["summary"]["compute_seconds"],
        )
        lines.append(
            f"| {row['system']} | {row['warmups_excluded']} | {row['repeats']} | "
            f"{compute['median_seconds']} | {total['median_seconds']} | "
            f"{total['p95_nearest_rank_seconds']} | {total['maximum_seconds']} | "
            f"{row['result_envelope_hash_stable']} |"
        )
    lines += [
        "",
        "计算字段包含time_basis及P8证据；西占额外含7天小时网格行运、次限和太阳回归，不能当成单一本命盘横向比较。",
        "每次原生输出均经当前源码指纹及请求绑定校验；没有缓存已排好的盘来缩短计算时间。",
        "本机共享其他夜间作业可能竞争CPU/磁盘；未固定电源计划或线程亲和性，未测服务容量。",
        "Python与平台、完整未四舍五入观测、输出hash和大小见同名JSON；没有读取或记录API密钥。",
        "模型0、服务器0、数据库写入0；不写前端模拟数据，不改v3计算或实验倒推阈值。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--chart-python", required=True)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20 or not 0 <= args.warmups <= 2:
        parser.error("performance_bounded_repeat_count_required")
    if args.output.suffix != ".json":
        parser.error("performance_json_output_required")
    report = {
        "schema": "p8-night24-synthetic-preview-performance-v1",
        "mode": "scripted",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "clock": "time.perf_counter",
        "timed_disk_writes": False,
        "http_api_or_model_sla": False,
        "model_calls": 0,
        "server_access": False,
        "systems": [],
    }
    for system in ("bazi", "ziwei", "astro"):
        value = measure_system(system, args.chart_python, args.repeats, args.warmups)
        report["systems"].append(value)
        print(
            json.dumps({"system": system, "summary": value["summary"]["total_seconds"]})
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf8",
        newline="\n",
    )
    args.output.with_suffix(".md").write_text(
        render_markdown(report), encoding="utf8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Reproducible dev-only source/memory/reflection/profile/report/revocation benchmark."""

import argparse
import hashlib
import json
import os
import socket
import sys
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mingjing_core.application.reflection_v3 import plan_reflection_work  # noqa: E402
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact  # noqa: E402
from mingjing_core.timekit.clock import SystemClock  # noqa: E402
from tests.v4.mod_final_pipeline.support_mod import (  # noqa: E402
    FIXTURE,
    SCOPE,
    current_records,
    pipeline,
    report,
)
from tests.v4.mod_final_pipeline.test_pipeline_mod import (  # noqa: E402
    AT,
    check_positive,
    private_text,
    render,
)
from tools.mod_week.performance import measure  # noqa: E402

FIXTURE_SHA256 = "90074adfba23e5d2ba0d8f049743ecb52bbf9dad4fcd37587a6565d172dfe5f5"
AREAS = ("daily", "career", "relationships", "family", "wellbeing", "finance", "metaphysics")
UNITS = 120


def prohibit_network(*args: object, **kwargs: object) -> None:
    raise RuntimeError("完整链离线性能观测禁止连接外部服务")


def isolate_process() -> None:
    for key in (
        "KIMI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MOONSHOT_API_KEY",
        "LANGSMITH_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "DASHSCOPE_API_KEY",
    ):
        os.environ.pop(key, None)
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    for name in ("socket", "create_connection", "getaddrinfo"):
        setattr(socket, name, prohibit_network)


def one_chain(material: dict[str, Any], index: int) -> None:
    area, zone = AREAS[index % len(AREAS)], material["zones"][index % 6]
    kind = ("weekly", "monthly", "quarterly")[index % 3]
    value = pipeline(material["texts"][area], AT + timedelta(seconds=index), area=area, timezone=zone)
    decision, document, cached, original = check_positive(value, kind)
    original_epoch, original_revision = value.snapshot.source_epoch, value.snapshot.revision
    changed = replace(value.snapshot, sources=(replace(value.source, revoked=True),))
    assert (changed.source_epoch, changed.revision) == (original_epoch, original_revision)
    current_work = plan_reflection_work(
        decision.intent,
        snapshot=changed,
        thread=value.thread,
        scope=SCOPE,
        clock=value.clock,
        permit=value.permit,
        profile=document,
        current_profile_revision=document.revision,
    )
    current_view = render(value, changed, document)
    current_report = report(value, current_records(cached, changed), kind=kind)
    assert current_work.status == "blocked" and current_work.rolling_summary is None
    assert not current_work.episodes and not current_work.profile_proposals
    assert not private_text(current_view) and value.source.text not in current_view.markdown
    assert not current_report.used_record_ids and value.source.text not in private_text(current_report)
    assert current_report.request_key != original.request_key
    rejected = False
    try:
        authorize_fact(value.snapshot.facts[0], changed, SCOPE)
    except MemoryGuardError:
        rejected = True
    assert rejected
    assert all(
        number == 0
        for value in (current_work, current_view, current_report)
        for number in asdict(value.effects).values()
    )


def workload(fixture: bytes) -> int:
    material = json.loads(fixture)
    assert material["synthetic_only"] is True and len(material["cases"]) == 41
    assert len(material["zones"]) == 6 and material["schema"] == "mod-final-pipeline-synthetic-v1"
    for index in range(UNITS):
        one_chain(material, index)
    return UNITS


def source_paths() -> tuple[Path, ...]:
    # Hashing all Core files catches dependency drift, including changes beyond the immediate import list.
    paths = set((ROOT / "mingjing_core").rglob("*.py"))
    paths.update((ROOT / "tests/v4/mod_final_pipeline").glob("*.py"))
    paths.update((Path(__file__), FIXTURE, ROOT / "tools/mod_week/performance.py"))
    return tuple(sorted(path.resolve() for path in paths))


def source_snapshot(paths: tuple[Path, ...]) -> dict[str, str]:
    return {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def output_target(value: Path) -> Path:
    target = value.resolve()
    if not target.is_relative_to(ROOT) or target.suffix != ".json" or target.exists():
        raise ValueError("完整链性能报告须为仓库内全新JSON")
    if not target.parent.is_dir() or not os.access(target.parent, os.W_OK):
        raise ValueError("完整链性能报告父目录须已存在且可写")
    return target


def benchmark(fixture: bytes, paths: tuple[Path, ...]) -> dict[str, Any]:
    if hashlib.sha256(fixture).hexdigest() != FIXTURE_SHA256 or b"\r\n" in fixture:
        raise ValueError("完整链合成材料已变化或不是冻结LF")
    before = source_snapshot(paths)
    result = measure("complete_source_to_report_then_revoke_120", lambda: workload(fixture), repeats=5)
    after = source_snapshot(paths)
    if before != after or source_paths() != paths:
        raise ValueError("完整链性能源码漂移，报告不可采信")
    result["timed_work"] = (
        "Fixture JSON decode; source/anchor and immutable memory inputs; plan/apply; reflection scheduling/work; "
        "8-section render; period content report; unchanged-epoch revocation; "
        "all stale outputs and fact rejection asserts"
    )
    result["excluded_preparation"] = "Module imports, fixture byte read, source hashing, report-file write"
    result["median_batch_ms_per_chain_equivalent"] = result["median_seconds"] * 1000 / UNITS
    return {
        "schema": "mod-final-pipeline-reproducible-v1",
        "observed_at": SystemClock().now().astimezone(ZoneInfo("Asia/Shanghai")).isoformat(),
        "kind": "synthetic_local_only",
        "python_version": sys.version,
        "dev_harness_only": True,
        "cases": [result],
        "fixture_sha256": FIXTURE_SHA256,
        "zones": json.loads(fixture)["zones"],
        "areas": list(AREAS),
        "source_count": len(paths),
        "source_stable": True,
        "source_sha256": before,
        "source_tree_sha256": hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "effects": {"real_model_calls": 0, "network_calls": 0, "pg_calls": 0, "notifications": 0, "runtime_writes": 0},
        "limitations": [
            "Development benchmark imports the frozen test harness; never a production dependency",
            "One full warmup, five untraced batch wall-clock samples, separate full tracemalloc run",
            "Input construction, current-source checks and assertions are timed",
            "Tracemalloc is Python allocations, not RSS; repeated workloads can benefit from caches",
            "Per-chain equivalent is batch throughput, not individual latency p50/p95",
            "Old MOD_final_pipeline_performance.json traced individual timings; no speedup comparison is valid",
            "No authenticated PG, real scheduler or external delivery was exercised",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    target = output_target(args.output)
    isolate_process()
    result = benchmark(FIXTURE.read_bytes(), source_paths())
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    case = result["cases"][0]
    print(
        case["name"],
        "median_batch_seconds",
        case["median_seconds"],
        "separate_peak_bytes",
        case["separate_tracemalloc_peak_bytes"],
    )


if __name__ == "__main__":
    main()

"""Synthetic sample and 1+10 direct-tool observations; no live mode exists."""

from __future__ import annotations

import argparse
import json
import platform
from collections.abc import Callable
from copy import deepcopy
from datetime import timedelta, timezone
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from ....timekit.clock import get_clock
from ..almanac import almanac
from ..daily_transit import daily_transit
from ..p8_worker import source_hashes
from ..synastry import synastry
from ..window_search import window_search
from .handoff_build import BIRTH
from .handoff_offline import offline_runtime

DAY = "2026-10-21"


def natal_pair() -> tuple[dict, dict]:
    a = dict(
        owner_user_id="synthetic-owner-ayuan",
        subject_id="synthetic-ayuan",
        revision=1,
        operation_id="synthetic-ayuan-night28-tools",
        birth=deepcopy(BIRTH),
    )
    b = dict(
        owner_user_id=a["owner_user_id"],
        subject_id="synthetic-xiaohe",
        revision=1,
        operation_id="synthetic-xiaohe-night28-tools",
        birth={
            "date": "1995-08-27",
            "reported_time": "14:10",
            "gender": "女",
            "place": {"tz": "Asia/Shanghai", "lon": 120.15, "lat": 30.28},
            "clock_basis": "clock",
            "precision": "reported",
        },
    )
    return a, b


def _observe(call: Callable[[], dict]) -> tuple[dict, dict]:
    call()
    observations = []
    for _ in range(10):
        start = perf_counter()
        result = call()
        observations.append(round((perf_counter() - start) * 1000, 6))
    return {
        "warmup_count": 1,
        "observation_count": 10,
        "milliseconds": observations,
        "min_ms": min(observations),
        "median_ms": median(observations),
        "mean_ms": mean(observations),
        "max_ms": max(observations),
        "payload_utf8_bytes": len(
            json.dumps(result, ensure_ascii=False).encode("utf8")
        ),
        "version": result["version"],
        "rule_hits": len(result["rule_hits"]),
    }, result


def _report(measured: dict) -> dict:
    return {
        "version": "p8-night28-tools-performance-v1",
        "mode": "scripted_synthetic",
        "recorded_at_beijing": get_clock()
        .now()
        .astimezone(timezone(timedelta(hours=8)))
        .isoformat(),
        "measurements": measured,
        "source_sha256": source_hashes(),
        "method": (
            "same Charts process; fresh natal preparation each daily/window/synastry call; "
            "warmed almanac source hash"
        ),
        "included": "calculation and evidence hashing/aliases; each window contains seven dates",
        "excluded": "interpreter start, Core worker transport, JSON serialization and file I/O",
        "model_calls": 0,
        "profile_writes": 0,
        "server_access": False,
        "limits": ["本机观测，不是HTTP chart_compute、SLA或现实预测效度。"],
    }


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
        newline="\n",
    )


def run(output: Path) -> dict:
    a, b = natal_pair()
    calls = {
        "daily_transit": lambda: daily_transit(a, DAY),
        "window_search": lambda: window_search(
            a, {"start_date": DAY, "end_date": "2026-10-27"}, "签约"
        ),
        "almanac": lambda: almanac(DAY),
        "synastry": lambda: synastry(
            a, b, "romantic", consent="user_confirmed", as_of_date=DAY
        ),
    }
    platform.system()
    measured, last = {}, {}
    with offline_runtime():
        for name, call in calls.items():
            measured[name], last[name] = _observe(call)
    _write(output / "night28-tools-performance.json", _report(measured))
    sample = Path("docs/v4/contracts/samples/synastry-ayuan-xiaohe.json")
    _write(sample, last["synastry"])
    inputs = sample.with_name("synastry-ayuan-xiaohe-input.json")
    _write(
        inputs,
        {
            "chart_a": a,
            "chart_b": b,
            "kind": "romantic",
            "consent": "user_confirmed",
            "as_of_date": DAY,
        },
    )
    return measured


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--output", type=Path, default=Path("docs/v4/evidence/P8"))
    args = parser.parse_args()
    print(json.dumps(run(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""42/3.2: actual synthetic 31/62/92-day searches, no model or network mode."""

from __future__ import annotations

import argparse
import json
import platform
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter

from ..p8_worker import source_hashes
from ..window_search import window_search
from .daily_transit_samples import sample_natal
from .handoff_offline import offline_runtime


def observe() -> dict:
    platform.system()
    rows = []
    with offline_runtime():
        for length in (31, 62, 92):
            interval = {
                "start_date": "2026-10-21",
                "end_date": (
                    date(2026, 10, 21) + timedelta(days=length - 1)
                ).isoformat(),
            }
            elapsed = []
            for _ in range(3):
                start = perf_counter()
                result = window_search(sample_natal(), interval, "签约", limit=31)
                elapsed.append(round(perf_counter() - start, 6))
                assert result["data"]["range"]["day_count"] == length
            rows.append(
                {
                    "days": length,
                    "observations": 3,
                    "seconds": elapsed,
                    "max_seconds": max(elapsed),
                }
            )
    return {
        "mode": "scripted_synthetic_actual_engine",
        "method": "serial same Charts process; fresh natal each call; no warmed result cache",
        "included": "calculation, all candidate dates, ranking, pagination, evidence aliases and content hashes",
        "excluded": "process start, Core transport, JSON serialization, HTTP and Agent",
        "measurements": rows,
        "recommended_agent_cap_days": 62 if rows[-1]["max_seconds"] > 30 else 92,
        "source_sha256": source_hashes(),
        "model_calls": 0,
        "profile_writes": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = observe()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in ("measurements", "recommended_agent_cap_days")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

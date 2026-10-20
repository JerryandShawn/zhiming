"""Generate one actual-computation synthetic preview without inference transports."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from ..window_search import window_search
from .handoff_build import BIRTH
from .handoff_offline import offline_runtime


def natal() -> dict:
    return {
        "owner_user_id": "synthetic-owner-ayuan",
        "subject_id": "synthetic-subject-ayuan",
        "revision": 1,
        "operation_id": "synthetic-window-ayuan-20261021",
        "birth": deepcopy(BIRTH),
    }


def _summary(output: Path, body: str, result: dict, duration: float) -> dict:
    return {
        "file": output.as_posix(),
        "sha256": hashlib.sha256(body.encode("utf8")).hexdigest(),
        "pretty_utf8_bytes": len(body.encode("utf8")),
        "compact_utf8_bytes": len(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        ),
        "elapsed_seconds": duration,
        "days": result["data"]["range"]["day_count"],
        "rule_hits": len(result["rule_hits"]),
        "pagination": result["data"]["pagination"],
        "trace": result["data"]["trace"],
        "candidates": [
            {"date": row["date"], "score": row["score"]}
            for row in result["data"]["candidates"][:7]
        ],
        "model_calls": result["effects"]["model_calls"],
        "writes": result["effects"]["writes"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scripted"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--measure-max-range", action="store_true")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=31)
    args = parser.parse_args()
    period = {"start_date": "2026-10-21", "end_date": "2026-10-27"}
    if args.measure_max_range:
        period["end_date"] = "2027-10-21"
    # Python's Windows platform cache may invoke a local version command on import.
    platform.uname()
    started = perf_counter()
    with offline_runtime():
        result = window_search(
            natal(), period, "签约", offset=args.offset, limit=args.limit
        )
    duration = perf_counter() - started
    body = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(body, encoding="utf8", newline="\n")
    print(
        json.dumps(
            _summary(args.output, body, result, duration), ensure_ascii=False, indent=2
        )
    )


if __name__ == "__main__":
    main()

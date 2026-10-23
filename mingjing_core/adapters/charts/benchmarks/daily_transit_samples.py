"""Generate seven actual-engine daily snapshots for the canonical synthetic 阿远."""

from __future__ import annotations

import argparse
import json
import platform
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..daily_transit import daily_transit_prepared, prepare_natal
from .handoff_build import BIRTH
from .handoff_offline import offline_runtime


def sample_natal() -> dict[str, Any]:
    return {
        "owner_user_id": "synthetic-owner-ayuan",
        "subject_id": "synthetic-subject-ayuan",
        "revision": 1,
        "operation_id": "synthetic-ayuan-daily-week-20261021",
        "birth": deepcopy(BIRTH),
    }


def generate(output: Path) -> dict[str, Any]:
    # Windows platform discovery may launch a local OS query on first import;
    # complete it before the strict child-process denylist, never weaken it.
    platform.system()
    output.mkdir(parents=True, exist_ok=True)
    start = date(2026, 10, 21)
    natal = sample_natal()
    files = []
    with offline_runtime():
        prepared = prepare_natal(natal, start.isoformat())
        for index in range(7):
            day = (start + timedelta(days=index)).isoformat()
            result = daily_transit_prepared(prepared, day)
            filename = f"ayuan_{day}.json"
            (output / filename).write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf8",
                newline="\n",
            )
            files.append(
                {
                    "file": filename,
                    "date": day,
                    "document_id": result["document_id"],
                    "hits": len(result["rule_hits"]),
                    "c": len(result["aliases"]["c"]),
                    "r": len(result["aliases"]["r"]),
                }
            )
    manifest = {
        "mode": "scripted_synthetic_actual_engine",
        "display_name": "阿远",
        "birth_fixture": "07号default_synthetic；沿用chart_compute同一合成人物",
        "version": "p8-daily-transit-v1",
        "snapshot": "each_explicit_date_12:00:00_UTC+08:00",
        "files": files,
        "real_model_requests": 0,
        "writes_to_profiles": 0,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf8",
        newline="\n",
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seven synthetic daily snapshots only")
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = generate(args.output)
    print(json.dumps({"files": len(result["files"]), "real_model_requests": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Opt-in isolated worker; existing worker and default output stay byte-identical."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.worker import bazi, load_engine  # noqa: E402
from mingjing_core.calculations.bazi import supplement  # noqa: E402
from mingjing_core.domain.json_values import ensure_finite_json  # noqa: E402


def source_hashes() -> dict[str, str]:
    paths = [Path(__file__), Path(__file__).with_name("p8_adapter.py")]
    paths += sorted((ROOT / "mingjing_core/calculations/bazi").glob("*.py"))
    paths += sorted((ROOT / "mingjing_core/knowledge/p8_bazi").glob("*.json"))
    # Normalize line endings only for the new cross-platform method fingerprint.
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in paths
    }


def calculate(args: dict[str, Any]) -> dict[str, Any]:
    result = bazi(args)
    result["data"]["p8"] = supplement(load_engine("bazi"), args, result["data"])
    result["metadata"]["versions"]["p8"] = {"version": "p8-calc-v1", "source_sha256": source_hashes()}
    result["metadata"]["actual_method"]["p8"] = {
        "entry": "P8ChartAdapter_explicit_only",
        "strength": "two_unreviewed_editorial_methods",
        "climate": "versioned_opening_excerpt_not_full_book_rules",
        "dayun_sect": 1,
        "default_v3_fields": "unchanged_before_existing_adapter_derivation",
    }
    result["metadata"]["warnings"].append("P8仅计算补充；编辑权重与摘表未获专家审核，不授权新的解释断语")
    return result


def main() -> None:
    request = json.load(sys.stdin)
    ensure_finite_json(request)
    if request.get("system") != "bazi":
        raise ValueError("P8 worker only supports bazi")
    allowed = ("datetime", "lng", "tz", "date", "gender", "lat")
    args = {key: request["args"][key] for key in allowed if key in request["args"]}
    result = calculate(args)
    ensure_finite_json(result)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()

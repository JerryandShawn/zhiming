"""Opt-in isolated worker; existing worker and default output stay byte-identical."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.jie_uncertainty import probe  # noqa: E402
from mingjing_core.adapters.charts.named_bazi import (  # noqa: E402
    named_supplement,  # noqa: E402
)
from mingjing_core.adapters.charts.p8_analysis import attach_analysis  # noqa: E402
from mingjing_core.adapters.charts.worker import bazi, load_engine  # noqa: E402
from mingjing_core.domain.json_values import ensure_finite_json  # noqa: E402


def source_hashes() -> dict[str, str]:
    paths = sorted(path for path in Path(__file__).parent.rglob("*.py") if "benchmarks" not in path.parts)
    paths += [ROOT / "hermes" / (name + ".py") for name in ("bazi", "ziwei", "astro")]
    paths += sorted((ROOT / "mingjing_core/calculations/bazi").glob("*.py"))
    paths += sorted((ROOT / "mingjing_core/knowledge/p8_bazi").glob("*.json"))
    paths += sorted((ROOT / "mingjing_core/knowledge/p8_ziwei").glob("*.json"))
    paths += sorted((ROOT / "mingjing_core/knowledge").glob("p8_*.json"))
    paths += [ROOT / "mingjing_core/knowledge/rectification_rules_v1.json"]
    # Normalize line endings only for the new cross-platform method fingerprint.
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for path in paths
    }


def calculate(args: dict[str, Any]) -> dict[str, Any]:
    result = bazi(args)
    result["data"]["p8"] = named_supplement(load_engine("bazi"), args, result["data"])
    attach_analysis(result["data"])
    result["metadata"]["versions"]["p8"] = {"version": "p8-calc-v3-rules", "source_sha256": source_hashes()}
    result["metadata"]["actual_method"]["p8"] = {
        "entry": "P8ChartAdapter_explicit_only",
        "strength": "two_project_v1_methods",
        "selected_schools": result["data"]["p8"]["selected_schools"],
        "climate": "versioned_opening_excerpt_not_full_book_rules",
        "dayun_sect": 1,
        "default_v3_fields": "unchanged_before_existing_adapter_derivation",
    }
    result["metadata"]["warnings"].append("P8具名口径；旺衰为项目口径v1，调候未经原刊校勘")
    return result


def main() -> None:
    request = json.load(sys.stdin)
    ensure_finite_json(request)
    from mingjing_core.adapters.charts.p8_pure_tools import PURE_TOOLS, calculate_pure_tool

    if request.get("system") in PURE_TOOLS:
        print(json.dumps(calculate_pure_tool(request["system"], request["args"]), ensure_ascii=False, allow_nan=False))
        return
    if request.get("system") == "transit_windows":
        from mingjing_core.adapters.charts.interactions_transits import transit_windows

        print(json.dumps(transit_windows(**request["args"]), ensure_ascii=False, allow_nan=False))
        return
    if request.get("system") == "time_basis":
        from mingjing_core.adapters.charts.time_basis_request import calculate_time_basis

        print(json.dumps(calculate_time_basis(request["args"]), ensure_ascii=False, allow_nan=False))
        return
    if request.get("system") == "western_timing":
        from mingjing_core.adapters.charts.western_timing import calculate_western_timing

        print(json.dumps(calculate_western_timing(request["args"]), ensure_ascii=False, allow_nan=False))
        return
    if request.get("system") == "jie_probe":
        args = request["args"]
        print(json.dumps(probe(load_engine("bazi"), args["datetime"], args["tz"]), ensure_ascii=False))
        return
    if request.get("system") != "bazi":
        raise ValueError("P8 worker only supports bazi")
    allowed = ("datetime", "lng", "tz", "date", "gender", "lat", "p8_options")
    args = {key: request["args"][key] for key in allowed if key in request["args"]}
    result = calculate(args)
    ensure_finite_json(result)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()

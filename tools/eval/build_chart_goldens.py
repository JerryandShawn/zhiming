"""Recompute C06 through the real, isolated chart adapter; never call a model."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.adapter import ChartAdapter  # noqa: E402
from tools.eval.chart_goldens import FIXTURE, HOURS, ChartGolden  # noqa: E402
from tools.eval.schema import load_scenario  # noqa: E402


def archive_for_c06() -> dict[str, Any]:
    scene = load_scenario(ROOT / "tools/eval/scenarios/C06.yaml")
    profiles = yaml.safe_load((ROOT / "tools/eval/fixtures/profiles.yaml").read_text(encoding="utf-8"))
    profile = deepcopy(profiles[scene.seed.profile])
    birth = {**profile["birth"], **scene.seed.profile_overrides["birth"]}
    return {
        "owner_user_id": "synthetic-c06",
        "subject_id": "self",
        "user": {
            "gender": {"male": "男", "female": "女"}[profile["gender"]],
            "birth": {
                "time_precision": "interval",
                "time_interval": {
                    "start": birth["date"] + " " + birth["interval_start"],
                    "end": birth["date"] + " " + birth["interval_end"],
                },
                "timezone_offset": 8,
                "location": {"lng": birth["longitude"], "lat": birth["latitude"], "city": birth["city"]},
            },
        },
    }


def project(result: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if result["errors"]:
        raise ValueError("C06 isolated calculation failed; no golden was written")
    samples, versions = [], None
    for artifact in result["artifacts"].values():
        profile = result["profiles"][artifact["profile_id"]]
        if versions is not None and versions != profile["versions"]:
            raise ValueError("Mixed chart versions cannot form one golden")
        versions = profile["versions"]
        data = artifact["data"]
        palace = next(p for p in data["palaces"] if p["name"] in {"命", "命宫"})
        samples.append(
            {
                "civil_datetime": profile["input"]["sample_civil_datetime"],
                "corrected_time": data["corrected_time"],
                "hour_index": data["method"]["hour_index"],
                "ming_gong": data["ming_gong"],
                "palace_ganzhi": palace["ganzhi"],
                "major_stars": [star["name"] for star in palace["major"]],
            }
        )
    if not samples or versions is None:
        raise ValueError("No calculated chart samples are available for a golden")
    return sorted(samples, key=lambda sample: sample["civil_datetime"]), versions


def calculate_golden(chart_python: str) -> ChartGolden:
    archive = archive_for_c06()
    adapter = ChartAdapter("synthetic-c06", python=chart_python)
    samples, versions = project(adapter.calculate(archive, "2026-10-17", ["ziwei"], 1, "self"))
    probes = []
    for point in ("1994-03-12 06:03", "1994-03-12 06:04"):
        exact = deepcopy(archive)
        exact["user"]["birth"].update(time_precision="exact", solar_datetime=point)
        projected, probe_versions = project(adapter.calculate(exact, "2026-10-17", ["ziwei"], 1, "self"))
        if probe_versions != versions:
            raise ValueError("Boundary probes must use the same chart versions")
        probes.extend(projected)
    grouped = {sample["hour_index"]: sample["major_stars"] for sample in samples}
    return ChartGolden.model_validate(
        {
            "version": "c06-ziwei-golden-v1",
            "scenario_id": "C06",
            "synthetic": True,
            "input": archive["user"],
            "versions": versions,
            "sampling": {
                "coverage": "sampled_not_continuous",
                "points": 5,
                "time_basis": "local_mean_solar_time_without_equation_of_time",
                "longitude_correction_minutes": round((archive["user"]["birth"]["location"]["lng"] - 120) * 4, 8),
            },
            "samples": samples,
            "boundary_probes": probes,
            "branches": [
                {"hour_index": hour, "label": HOURS[hour] + "时", "major_stars": stars}
                for hour, stars in sorted(grouped.items())
            ],
            "sampled_stable": len({tuple(sorted(sample["major_stars"])) for sample in samples}) == 1,
            "external_cross_check": "deferred_to_P8",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chart-python", default=os.getenv("CHART_PYTHON"))
    parser.add_argument("--output", type=Path, default=FIXTURE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not args.chart_python:
        parser.error("Provide the isolated Charts interpreter through --chart-python or CHART_PYTHON")
    actual = calculate_golden(str(Path(args.chart_python).resolve()))
    if args.check:
        expected = ChartGolden.model_validate(yaml.safe_load(args.output.read_text(encoding="utf-8")))
        if actual != expected:
            raise SystemExit("C06 golden drifted; review engine versions and calculated observations")
    else:
        args.output.write_text(
            yaml.safe_dump(actual.model_dump(), allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    print(json.dumps({"scenario": "C06", "samples": len(actual.samples), "sampled_stable": actual.sampled_stable}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

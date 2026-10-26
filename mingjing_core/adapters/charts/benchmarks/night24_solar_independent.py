"""Night 24 bounded independent EOT study; never changes a production calculation."""

from __future__ import annotations

import argparse
import json
import os
from time import perf_counter
from typing import Any

from .night24_solar_boundaries import boundary_probes
from .night24_solar_reference import (
    DATES,
    SOURCES,
    THRESHOLD_SECONDS,
    TIMES,
    SwissReference,
    digest,
    grid,
    iso,
    summarize,
)

METRICS = (
    "noaa_minus_swiss_eot_seconds",
    "noaa_minus_swiss_same_label_seconds",
    "swiss_label_minus_UT1_eot_seconds",
    "swiss_inferred_UT1_minus_UTC_seconds",
    "noaa_minus_swiss_apparent_clock_seconds",
)


def run() -> dict[str, Any]:
    started = perf_counter()
    reference = SwissReference()
    moments = grid()
    rows = [reference.compare(moment) for moment in moments]
    stats = {metric: summarize([row[metric] for row in rows]) for metric in METRICS}
    worst = sorted(
        rows, key=lambda row: abs(row["noaa_minus_swiss_eot_seconds"]), reverse=True
    )[:10]
    boundary = boundary_probes(reference)
    report = _report(rows, moments, stats, worst, boundary, reference.metadata())
    report["elapsed_seconds"] = perf_counter() - started
    return report


def _grid_metadata(rows: list[dict[str, Any]], moments: list[Any]) -> dict[str, Any]:
    return {
        "year_start_inclusive": 1901,
        "year_end_inclusive": 2099,
        "dates_each_year": DATES,
        "UTC_times": TIMES,
        "additional_days": "Feb29 in every Gregorian leap year",
        "sample_count": len(rows),
        "ordered_UTC_grid_sha256": digest([iso(moment) for moment in moments]),
        "all_comparison_rows_sha256": digest(rows),
        "first": rows[0]["actual_UTC"],
        "last": rows[-1]["actual_UTC"],
    }


def _report(
    rows: list[dict[str, Any]],
    moments: list[Any],
    stats: dict[str, Any],
    worst: list[dict[str, Any]],
    boundary: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": "night24-solar-independent-v1",
        "fixed_alarm_seconds": THRESHOLD_SECONDS,
        "status": "offline_research_not_product_acceptance",
        "live_model_calls": 0,
        "network_calls": 0,
        "database_writes": 0,
        "production_method_changed": False,
        "sources": SOURCES,
        "documentation_conflict": {
            "manual_section_18_3_11": "summary calls input tjd_et ephemeris time",
            "resolved_by": "manual section9.4, wrapper docstring and versioned C implementation all require UT",
            "reference_input_used": "JD_UT1 from Swiss utc_to_jd, never the returned JD_TT",
        },
        "grid": _grid_metadata(rows, moments),
        "statistics": stats,
        "worst_ten_by_absolute_eot_difference": worst,
        "per_year_max_absolute_eot_difference_seconds": {
            str(year): max(
                abs(row["noaa_minus_swiss_eot_seconds"])
                for row in rows
                if row["actual_UTC"].startswith(str(year))
            )
            for year in range(1901, 2100)
        },
        "boundary_study": boundary,
        "reference": reference,
        "limits": [
            "固定5秒是抽样研究报警门槛，不是生产验收、物理准确度或时柱可靠度保证；超限照实保留。",
            "8156点不是逐日或连续覆盖。Swiss与NOAA属于不同数值实现，不是独立天文观测。",
            "time_equ没有flags输出；伴随calc_ut的Moshier标志只能作为所设置会话的旁证。",
            "Swiss的UT1由其Delta-T/闰秒模型推算，并非IERS实测；1972年前及未来UTC有模型限制。",
            "现实现UTC近似平太阳时，Swiss参考钟坐标额外包含推算DUT1；公式差与时标差分别报告。",
            "边界两套坐标使用同一lunar-python排柱；临界差异不证明某套人生解释更真，不自动更换默认算法。",
            "本研究不改变资料、v3、默认均时差算法或用户界面，不触发真实模型请求。",
        ],
    }


def main() -> None:
    for name in tuple(os.environ):
        if name.endswith("API_KEY"):
            os.environ.pop(name, None)
    os.environ.update(LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false")
    parser = argparse.ArgumentParser(
        description="Offline fixed-grid equation-of-time comparison"
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run()
    with open(args.output, "w", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")
    print(
        json.dumps(
            {
                "samples": report["grid"]["sample_count"],
                "elapsed_seconds": report["elapsed_seconds"],
                "fixed_alarm_seconds": report["fixed_alarm_seconds"],
                "eot": report["statistics"]["noaa_minus_swiss_eot_seconds"],
                "boundary_disagreements": report["boundary_study"][
                    "day_hour_disagreements"
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

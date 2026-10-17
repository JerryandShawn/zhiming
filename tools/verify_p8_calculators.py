"""Offline synthetic P8 verification, optionally against a separate sxtwl build."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import io
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mingjing_core.adapters.charts.p8_worker import source_hashes  # noqa: E402
from mingjing_core.adapters.charts.worker import load_engine  # noqa: E402
from mingjing_core.calculations.bazi.elements import BRANCHES, HIDDEN, STEMS, table  # noqa: E402


def tests() -> dict[str, Any]:
    # Missing chart dependencies are errors, never optional skips in this check.
    import lunar_python  # noqa: F401

    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_p8_native_calculations.py")
    result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
    return {
        "tests": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "successful": result.wasSuccessful() and not result.skipped,
    }


def gz(value: Any) -> str:
    return STEMS[value.tg] + BRANCHES[value.dz]


def pillars_crosscheck(reference: Any, engine: Any) -> dict[str, Any]:
    observations, mismatches = [], []
    for year in (1950, 1984, 2000, 2012, 2026, 2040):
        for month in range(1, 13):
            # Noon on the 15th avoids both midnight and a Jie calendar date.
            date = datetime(year, month, 15, 12)
            lunar = engine.Solar.fromYmdHms(year, month, 15, 12, 0, 0).getLunar()
            eight = lunar.getEightChar()
            eight.setSect(2)
            native = [eight.getYear(), eight.getMonth(), eight.getDay(), eight.getTime()]
            other = reference.fromSolar(year, month, 15)
            independent = [
                gz(other.getYearGZ(False)),
                gz(other.getMonthGZ()),
                gz(other.getDayGZ()),
                gz(other.getHourGZ(12)),
            ]
            row = {"date": date.isoformat() + "+08:00", "lunar_python": native, "sxtwl": independent}
            observations.append(row)
            if native != independent:
                mismatches.append(row)
    return {
        "samples": len(observations),
        "pillar_comparisons": len(observations) * 4,
        "mismatches": mismatches,
        "observations": observations,
        "scope": "UTC+8 civil noon, no longitude correction, away from Jie date; not all instants verified",
    }


def jie_crosscheck(reference: Any, engine: Any) -> dict[str, Any]:
    rows = []
    names = (
        "冬至",
        "小寒",
        "大寒",
        "立春",
        "雨水",
        "惊蛰",
        "春分",
        "清明",
        "谷雨",
        "立夏",
        "小满",
        "芒种",
        "夏至",
        "小暑",
        "大暑",
        "立秋",
        "处暑",
        "白露",
        "秋分",
        "寒露",
        "霜降",
        "立冬",
        "小雪",
        "大雪",
    )
    for year in (2012, 2026):
        native = engine.Solar.fromYmdHms(year, 7, 1, 12, 0, 0).getLunar().getJieQiTable()
        for item in reference.getJieQiByYear(year):
            if item.jqIndex % 2 == 0:
                continue
            civil = reference.JD2DD(item.jd)
            point = datetime(civil.Y, civil.M, civil.D, int(civil.h), int(civil.m)) + timedelta(seconds=civil.s)
            name = names[item.jqIndex]
            if point.year != year:
                name = {"小寒": "XIAO_HAN", "立春": "LI_CHUN", "惊蛰": "JING_ZHE"}.get(name, name)
            if name not in native:
                continue
            native_point = datetime.fromisoformat(native[name].toYmdHms())
            rows.append(
                {
                    "year": year,
                    "jie": name,
                    "lunar_python": native_point.isoformat() + "+08:00",
                    "sxtwl": point.isoformat() + "+08:00",
                    "delta_seconds": round((native_point - point).total_seconds(), 6),
                }
            )
    return {
        "samples": len(rows),
        "observations": rows,
        "max_absolute_delta_seconds": max(abs(row["delta_seconds"]) for row in rows),
        "decision": "Differences recorded for brain; no default engine/boundary/golden changed",
    }


def reference_check(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        raise ValueError("Independent reference directory is required")
    sys.path.insert(0, str(path.resolve()))
    import sxtwl

    files = sorted([*path.glob("*.pyd"), *path.glob("*.so"), path / "sxtwl.py"])
    engine = load_engine("bazi")
    return {
        "status": "executed",
        "reference": "sxtwl",
        "version": importlib.metadata.version("sxtwl"),
        "source": "https://github.com/yuangu/sxtwl_cpp",
        "package": "https://pypi.org/project/sxtwl/2.0.7/",
        "file_sha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
        "pillars": pillars_crosscheck(sxtwl, engine),
        "jie": jie_crosscheck(sxtwl, engine),
    }


def knowledge_audit() -> dict[str, Any]:
    from lunar_python.util import LunarUtil

    climate = table("climate")
    rows = climate["rows"]
    statuses = sorted({row["extraction_status"] for row in rows.values()})
    differences = [
        {"branch": branch, "v3_adapter_order": list(hidden), "lunar_python_order": LunarUtil.ZHI_HIDE_GAN[branch]}
        for branch, hidden in HIDDEN.items()
        if list(hidden) != LunarUtil.ZHI_HIDE_GAN[branch]
    ]
    return {
        "climate_rows": len(rows),
        "climate_extraction_counts": {
            status: sum(row["extraction_status"] == status for row in rows.values()) for status in statuses
        },
        "full_classic_rule_verification": False,
        "climate_special_fallback": {
            "key": "乙丑",
            "basis": "winter general rule, not a separate twelfth-month paragraph",
        },
        "hidden_order_differences": differences,
        "distinct_auxiliary_markers": 8,
        "strength_weights": "original_editorial_unreviewed; arithmetic tested, metaphysical validity not established",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-path", type=Path, help="Read-only isolated sxtwl 2.0.7 target directory")
    parser.add_argument("--require-independent", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.require_independent and not args.reference_path:
        parser.error("--require-independent needs --reference-path")
    native = tests()
    reference = reference_check(args.reference_path) if args.reference_path else {"status": "not_run"}
    report = {
        "schema": "p8-calculation-evidence-v1",
        "synthetic_only": True,
        "model_calls": 0,
        "native_tests": native,
        "source_sha256": source_hashes(),
        "knowledge_audit": knowledge_audit(),
        "independent_reference": reference,
        "limits": [
            "Reference matches verify sampled calendar/arithmetic only, not predictions",
            "No skills/tools, old-analysis recalculation, database, channel or server exercised",
        ],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "native_tests": native,
                "independent_status": reference["status"],
                "calendar_mismatches": len(reference.get("pillars", {}).get("mismatches", [])),
                "jie_max_delta_seconds": reference.get("jie", {}).get("max_absolute_delta_seconds"),
            },
            ensure_ascii=False,
        )
    )
    return 0 if native["successful"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

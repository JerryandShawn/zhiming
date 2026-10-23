"""Metadata-only chronology audit; never redraw the fixed donor assignment."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .eligibility_v2 import question_year
from .night28_controls import SEED, rehearse_controls, same_source_placebo
from .records import BirthMetadata, Question, fingerprint


def temporal_order(birth: BirthMetadata, target_year: int) -> str:
    if type(target_year) is not int or not 1600 <= target_year <= 2199:
        raise ValueError("temporal_preflight_target_year_invalid")
    if birth.calendar != "solar":
        return "birth_calendar_not_explicit_solar"
    if birth.year is not None and birth.year != target_year:
        return (
            "birth_definitely_after_annual_snapshot"
            if birth.year > target_year
            else "birth_definitely_not_after_annual_snapshot"
        )
    fields = (birth.year, birth.month, birth.day, birth.hour, birth.minute)
    if any(value is None for value in fields):
        return "birth_fields_incomplete"
    moment = datetime(*fields)  # type: ignore[arg-type]
    target = datetime(target_year, 7, 1, 4)
    # Verified historical UTC offsets are absent here. Use the whole allowed
    # [-14,+14] hour range; never invent a location or select an offset.
    if moment - timedelta(hours=14) > target:
        return "birth_definitely_after_annual_snapshot"
    if moment + timedelta(hours=14) <= target:
        return "birth_definitely_not_after_annual_snapshot"
    return "verified_timezone_required_to_order_instants"


def temporal_preflight(records: list[Question], seed: int = SEED) -> dict[str, Any]:
    placebo = same_source_placebo(records, seed)
    pairs = rehearse_controls(records, seed)["pairs"]
    rows = []
    for original, swapped, pair in zip(records, placebo, pairs, strict=True):
        target = question_year(original).year
        if target is None:
            raise ValueError("temporal_preflight_explicit_question_year_required")
        rows.append(
            {
                "question_identity_sha256": pair["question_identity_sha256"],
                "case_identity_sha256": pair["case_identity_sha256"],
                "donor_case_identity_sha256": pair["donor_case_identity_sha256"],
                "donor_birth_year_after_target_year": None
                if swapped.birth.year is None
                else swapped.birth.year > target,
                "donor_temporal_order": temporal_order(swapped.birth, target),
                "original_temporal_order": temporal_order(original.birth, target),
            }
        )
    return {
        "contract": "e2-night28-fixed-donor-temporal-preflight-v1",
        "seed": seed,
        "sampling_basis": "annual_basis_question_year_July01_noon_UTC+08:00",
        "questions": len(records),
        "donor_birth_year_after_target_year_count": sum(
            row["donor_birth_year_after_target_year"] is True for row in rows
        ),
        "donor_temporal_order_counts": dict(
            Counter(row["donor_temporal_order"] for row in rows)
        ),
        "original_temporal_order_counts": dict(
            Counter(row["original_temporal_order"] for row in rows)
        ),
        "pair_assignment_sha256": fingerprint(pairs),
        "pair_audit": rows,
        "matching_changed": False,
        "seed_changed": False,
        "retries": 0,
        "chart_calculations": 0,
        "real_model_requests": 0,
        "chart_preflight_executed": False,
        "complete_chart_calculability_established": False,
        "limits": [
            "宽松对照的输入结构可构建，不等于每题可排盘；不为修复时间先后关系而重抽、改年份或删题。",
            "仅按源出生元数据与既有07-01正午年度采样检查先后，不推造未确认地理、时区或缺失分钟。",
            "非阳历或缺字段题保持未判；没有输出任何出生数值、出生哈希、题面或答案。",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    from .night24_sources import audit_source

    parser = argparse.ArgumentParser(description="Fixed-donor chronology metadata only")
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--mingli-root", type=Path, required=True)
    parser.add_argument("--baziqa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.suffix != ".json" or any(
        args.output.resolve().is_relative_to(root.resolve())
        for root in (args.mingli_root, args.baziqa_root)
    ):
        parser.exit(2, "e2_temporal_output_must_not_overlap_source_cache\n")
    try:
        records = []
        for root, source in (
            (args.mingli_root, "mingli"),
            (args.baziqa_root, "baziqa"),
        ):
            _, selected = audit_source(root, source)
            records.extend(selected)
        report = temporal_preflight(records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf8",
            newline="\n",
        )
    except (ValueError, OSError):
        parser.exit(2, "e2_temporal_metadata_preflight_failed\n")
    print(
        json.dumps(
            {
                "questions": report["questions"],
                "after_target_year": report["donor_birth_year_after_target_year_count"],
                "model_calls": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

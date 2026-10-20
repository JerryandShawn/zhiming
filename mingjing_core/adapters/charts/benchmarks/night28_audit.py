"""Read local E2 caches and rehearse Brain28 controls without charts or models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .night24_audit import _assembled_report
from .night24_placebo import placebo_preflight
from .night24_sources import audit_source
from .night28_controls import CONTROL_NAME, SEED, rehearse_controls, rehearse_no_chart
from .records import Question

SAFE_ERRORS = frozenset(
    {
        "relaxed_placebo_explicit_question_year_required",
        "relaxed_placebo_duplicate_question_identity",
        "relaxed_placebo_case_birth_conflict",
        "relaxed_placebo_integer_seed_required",
        "same_source_distinct_birth_matching_unavailable",
    }
)


def _rehearsal(records: list[Question]) -> dict[str, Any]:
    try:
        return rehearse_controls(records, SEED)
    except Exception as error:
        code = str(error) if type(error) is ValueError else ""
        return {
            "control_name": CONTROL_NAME,
            "seed": SEED,
            "status": "unavailable",
            "error_code": code
            if code in SAFE_ERRORS
            else "e2_control_rehearsal_failed",
            "questions": len(records),
            "placebo_inputs_built": 0,
            "no_chart_inputs_built": 0,
            "professional_corpus_scores": None,
            "real_model_requests": 0,
            "chart_calculations": 0,
            "inference_calls": 0,
        }


def build_audit(mingli_root: Path, baziqa_root: Path) -> dict[str, Any]:
    sources, records = [], []
    for root, source in ((mingli_root, "mingli"), (baziqa_root, "baziqa")):
        report, selected = audit_source(root, source)
        sources.append(report)
        records.extend(selected)
    report = _assembled_report(sources, placebo_preflight(records))
    report["contract"] = "e2-night28-scripted-controls-v1"
    report["historical_strict_control"] = report.pop("placebo_preflight")
    report["current_controls"] = _rehearsal(records)
    report["no_chart_control"] = rehearse_no_chart(records, SEED)
    report["historical_synthetic_workflow"] = report.pop("synthetic_workflow")
    report["current_workflow"] = {
        "policy": "brain28_M2",
        "executed_by_this_audit": True,
        "steps": [
            "全来源结构验证后筛选2025赛季，按明确题面目标年纳入。",
            "固定种子对同源纳入案例作一对一出生错配，保留原题与目标年。",
            "按同一选项置换构造无盘对照，仅原题与选项，答案映射留在评分侧。",
            "核对案例一致性、出生变化、原题/目标年/选项一致性，仅发布哈希和计数。",
        ],
        "repeats": 1,
        "inference_calls": 0,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    from .night28_markdown import render_markdown

    parser = argparse.ArgumentParser(description="Local E2 Brain28 control rehearsal")
    parser.add_argument("--mode", choices=("scripted",), required=True)
    parser.add_argument("--mingli-root", type=Path, required=True)
    parser.add_argument("--baziqa-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.suffix != ".json" or any(
        args.output.resolve().is_relative_to(root.resolve())
        for root in (args.mingli_root, args.baziqa_root)
    ):
        parser.exit(2, "e2_audit_output_must_not_overlap_source_cache\n")
    try:
        report = build_audit(args.mingli_root, args.baziqa_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        args.output.with_suffix(".md").write_text(
            render_markdown(report), encoding="utf-8", newline="\n"
        )
    except (ValueError, OSError):
        parser.exit(2, "e2_local_control_audit_failed\n")
    print(
        json.dumps(
            {"mode": "scripted", "counts": report["counts"], "model_requests": 0}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Scripted-only local-corpus audit; no provider, chart engine or live mode."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .night24_placebo import placebo_preflight
from .night24_sources import audit_source
from .protocol_v2 import CONFIGURATIONS_V2
from .scripted_v2 import DISCLAIMER


def _synthetic_workflow() -> dict[str, Any]:
    return {
        "executed_by_this_audit": False,
        "questions": 3,
        "source": "explicitly_synthetic_v2",
        "entry_point": "mingjing_core.adapters.charts.benchmarks.scripted_v2",
        "configurations": list(CONFIGURATIONS_V2),
        "steps": [
            "fixtures()生成3道显式2025年合成时支读数题，不取专业题库正文。",
            "固定种子打乱选项，评分器保管正确选项映射，推理回调不接触答案。",
            "C0无盘；C1盘面文字；C2结构化盘与技能；C3增加当前规则命中。",
            "C4a按时间交互顺序生成专科请求；C4b不附顺序约束，再用脚本合参。",
            "同题目标年安慰剂在3合成案例间固定错配，再与C3脚本读数比较。",
            "现有scripted_v2另含比赛年口径兼容烟测，仅历史对照，不充当当前控制。",
        ],
        "repeat_policy": "本次仅写流程；既有脚本为每题1次，不把5次多数票说成已运行。",
        "interpretation": "脚本读盘面字段只验证软件流程，不验证命理推理或现实预测。",
        "professional_corpus_execution": False,
        "real_provider_or_agent": False,
        "real_model_requests": 0,
        "chart_calculations_in_this_audit": 0,
    }


def build_audit(mingli_root: Path, baziqa_root: Path) -> dict[str, Any]:
    sources, records = [], []
    for root, source in ((mingli_root, "mingli"), (baziqa_root, "baziqa")):
        report, selected = audit_source(root, source)
        sources.append(report)
        records.extend(selected)
    return _assembled_report(sources, placebo_preflight(records))


def _assembled_report(
    sources: list[dict[str, Any]], placebo: dict[str, Any]
) -> dict[str, Any]:
    included = [
        row
        for source in sources
        for f in source["files"]
        for row in f["included_audit"]
    ]
    excluded = [
        row
        for source in sources
        for f in source["files"]
        for row in f["excluded_audit"]
    ]
    counts = {
        "full_source_questions": sum(s["full_source_questions"] for s in sources),
        "subset_source_questions": sum(s["subset_source_questions"] for s in sources),
        "included_questions": len(included),
        "excluded_questions": len(excluded),
    }
    return {
        "contract": "e2-night24-scripted-audit-v1",
        "disclaimer": DISCLAIMER,
        "mode": "scripted",
        "competition_year_filter": 2025,
        "year_basis": "question_explicit_target_year",
        "evidence_span_indexing": "python_str_unicode_codepoints_zero_based_half_open",
        "metadata_year_fallback": False,
        "counts": counts,
        "reference_counts_match": (
            counts["subset_source_questions"] == 80
            and counts["included_questions"] == 14
            and counts["excluded_questions"] == 66
        ),
        "included_audit": included,
        "excluded_audit": excluded,
        "excluded_reasons": dict(Counter(row["reason"] for row in excluded)),
        "target_years": sorted({row["question_target_year"] for row in included}),
        "target_year_equals_competition_year_count": sum(
            row["question_target_year"] == row["competition_year"] for row in included
        ),
        "sources": sources,
        "placebo_preflight": placebo,
        "synthetic_workflow": _synthetic_workflow(),
        "professional_corpus_scores": None,
        "professional_corpus_confidence_interval": None,
        "source_content_redistributed": False,
        "real_model_requests": 0,
        "chart_calculations": 0,
        "new_downloads": 0,
        "server_requests": 0,
    }


def main(argv: list[str] | None = None) -> int:
    from .night24_markdown import render_markdown

    parser = argparse.ArgumentParser(description="Local hash-only E2 audit")
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
    except ValueError:
        parser.exit(2, "e2_local_source_audit_failed\n")
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        args.output.with_suffix(".md").write_text(
            render_markdown(report), encoding="utf-8", newline="\n"
        )
    except OSError:
        parser.exit(2, "e2_audit_output_failed\n")
    print(
        json.dumps(
            {"mode": "scripted", "counts": report["counts"], "model_requests": 0}
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

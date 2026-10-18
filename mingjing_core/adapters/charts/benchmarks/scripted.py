"""Historical deprecated E2 v1 smoke; use scripted_v2 for current C0-C4 plans."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from .engine import P8Engine
from .experiment import (
    CONFIGURATIONS,
    InferenceRequest,
    placebo_births,
    run_configuration,
)
from .loaders import inspect_corpus
from .records import BirthMetadata, CalculationInputs, Question, fingerprint

LIMITATION = (
    "比赛题只测与职业命理师判断的一致性，不是现实预测的效度；"
    "本次合成盘面读数更不构成命理推理得分。"
)


def synthetic_questions() -> list[Question]:
    options = tuple(zip("ABCD", ("辰", "未", "戌", "丑"), strict=True))
    dates = ((1990, 1, 15, 8), (1991, 7, 21, 14), (1992, 11, 3, 20), (1993, 12, 17, 2))
    return [
        Question(
            id=f"synthetic-{index}",
            case_id=f"synthetic-case-{index}",
            text="合成流转测试：注入盘面中的时支是哪一个？",
            options=options,
            answer="ABCD"[index],
            birth=BirthMetadata(
                year, month, day, hour, 0, "男", "合成坐标：东经120度", "solar", False
            ),
            source="project_synthetic_chart_reading_fixture",
        )
        for index, (year, month, day, hour) in enumerate(dates)
    ]


def chart_reading_answerer(request: InferenceRequest) -> str:
    """Deliberately reads one field; it performs no life-event interpretation."""
    if request.stage == "specialist":
        return "脚本专科阶段只确认 /data/pillars/hour/zhi，未运行专科 Agent。"
    artifact = next(iter(request.chart["artifacts"].values()))
    branch = artifact["data"]["pillars"]["hour"]["zhi"]
    matches = [
        letter for letter, text in request.question["options"].items() if text == branch
    ]
    if len(matches) != 1:
        raise ValueError("synthetic_chart_reading_has_no_unique_option")
    return matches[0]


def smoke_run(python: str) -> dict[str, Any]:
    questions = synthetic_questions()
    inputs = {
        fingerprint(row.birth.public_input()): CalculationInputs(
            120.0, 8.0, "explicit_synthetic_fixture_v1", True
        )
        for row in questions
    }
    engine = P8Engine(python, inputs, "2026-10-18")
    controls = {
        "original": questions,
        "shuffled_birth_placebo": placebo_births(questions, seed=20261018),
    }
    results = [
        run_configuration(
            rows,
            configuration,
            engine,
            chart_reading_answerer,
            control=control,
            execution_kind="scripted_synthetic_chart_field_reading",
        )
        for control, rows in controls.items()
        for configuration in CONFIGURATIONS
    ]
    return {
        "mode": "scripted",
        "real_model_requests": 0,
        "professional_corpus_score": None,
        "agent_protocols": "request_plans_only_not_live_v4_runtime",
        "placebo_seed": 20261018,
        "synthetic_questions": len(questions),
        "isolated_chart_calculations": len(engine.cache),
        "answer_key_sent_to_answerer": False,
        "results": results,
        "calculation_provenance": [
            {
                "birth_fingerprint": key,
                "chart_fingerprint": fingerprint(chart),
                "profiles": [
                    {
                        "actual_method": profile["actual_method"],
                        "versions": profile["versions"],
                    }
                    for profile in chart["profiles"].values()
                ],
            }
            for key, chart in engine.cache.items()
        ],
        "limitation": LIMITATION,
    }


def _source(root: Path, source: str) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    paths = (
        [root / "data/data.json"]
        if source == "mingli"
        else sorted((root / "data").glob("contest8_*.json"))
    )
    if not paths:
        raise ValueError("source_corpus_files_missing")
    files = [inspect_corpus(path, source) for path in paths]
    license_file = root / "LICENSE"
    dirty = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "source": source,
        "commit": commit,
        "source_working_tree_clean": not bool(dirty),
        "files": files,
        "normalized_question_total": sum(row["questions"] for row in files),
        "all_files_normalized": all(
            row["parse_status"] == "normalized" for row in files
        ),
        "blocked_files": [
            row["file"] for row in files if row["parse_status"] != "normalized"
        ],
        "license": "MIT_independent_LICENSE"
        if license_file.is_file()
        else "README_claims_MIT_no_LICENSE_file",
        "license_sha256": hashlib.sha256(license_file.read_bytes()).hexdigest()
        if license_file.is_file()
        else None,
        "readme_sha256": hashlib.sha256((root / "README.md").read_bytes()).hexdigest(),
        "data_policy": "local_ignored_private_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2 only-scripted preparation; there is no live-model path"
    )
    parser.add_argument("--mode", choices=("scripted",), default="scripted")
    parser.add_argument("--chart-python", required=True)
    parser.add_argument("--mingli-root", type=Path)
    parser.add_argument("--baziqa-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = smoke_run(args.chart_python)
    report["source_schema_inspections"] = [
        _source(root, source)
        for root, source in ((args.mingli_root, "mingli"), (args.baziqa_root, "baziqa"))
        if root
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "mode": report["mode"],
                "real_model_requests": 0,
                "synthetic_questions": report["synthetic_questions"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

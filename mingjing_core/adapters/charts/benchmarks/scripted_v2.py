"""Three synthetic questions exercise C0-C4 and same-year placebo without models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ....skills.loader import chart_skill
from .controls_v2 import same_year_placebo
from .engine import P8Engine
from .protocol_v2 import CONFIGURATIONS_V2, RequestV2, run_configuration_v2
from .records import BirthMetadata, CalculationInputs, Question, fingerprint
from .statistics_v2 import paired_comparison

DISCLAIMER = (
    "本评测衡量的是与命理比赛标准答案的一致性，不是现实预测的效度；"
    "2025 年比赛题可能已进入 2026 年发布模型的训练数据；"
    "40 题量级的子集，95% 置信区间约为 ±15 个百分点。"
)


def fixtures() -> list[Question]:
    dates = ((1, 15, 8), (7, 21, 14), (11, 3, 20))
    return [
        Question(
            id=f"synthetic-v2-{index}",
            case_id=f"synthetic-v2-case-{index}",
            text="合成软件测试：程序盘面的时支是哪一个？",
            options=tuple(zip("ABCD", ("辰", "未", "戌", "丑"), strict=True)),
            answer="ABC"[index],
            birth=BirthMetadata(
                1990, month, day, hour, 0, "男", "合成东经120度", "solar", False
            ),
            source="explicitly_synthetic_v2",
            competition_year=2025,
        )
        for index, (month, day, hour) in enumerate(dates)
    ]


def answerer(request: RequestV2) -> str:
    if request.stage == "specialist":
        return '{"claims":[],"gaps":["合成阶段测试，没有运行真实专科Agent"]}'
    if request.configuration == "C0":
        return "A"
    data = (
        json.loads(request.chart_text)[0]
        if request.chart_text
        else next(iter(request.chart_bundle["artifacts"].values()))["data"]
    )
    branch = data["pillars"]["hour"]["zhi"]
    choices = [
        letter for letter, text in request.question["options"].items() if text == branch
    ]
    if len(choices) != 1:
        raise ValueError("synthetic_question_does_not_match_chart_field")
    return choices[0]


def _skill(system: str) -> dict[str, Any]:
    return chart_skill(system, "basics")


def run_scripted_v2(python: str) -> dict[str, Any]:
    records = fixtures()
    inputs = {
        fingerprint(row.birth.public_input()): CalculationInputs(
            120, 8, "synthetic_v2_explicit_input", True
        )
        for row in records
    }
    engine = P8Engine(python, inputs, "2026-10-18")
    results = {
        configuration: run_configuration_v2(
            records, configuration, engine, _skill, answerer, seed=20261018
        )
        for configuration in CONFIGURATIONS_V2
    }
    placebo = run_configuration_v2(
        same_year_placebo(records, 20261018, year_basis="birth_year"),
        "C3",
        engine,
        _skill,
        answerer,
        seed=20261018,
        control="same_birth_year_chart_placebo",
    )
    placebo["year_basis"] = "birth_year"
    other_placebo = run_configuration_v2(
        same_year_placebo(records, 20261018, year_basis="competition_year"),
        "C3",
        engine,
        _skill,
        answerer,
        seed=20261018,
        control="same_competition_year_chart_placebo",
    )
    other_placebo["year_basis"] = "competition_year"
    pairs = (
        ("C0", "C1"),
        ("C1", "C2"),
        ("C2", "C3"),
        ("C3", "C4a"),
        ("C3", "C4b"),
        ("C4a", "C4b"),
    )
    comparisons = {
        f"{left}_to_{right}": paired_comparison(
            results[left]["outcomes"], results[right]["outcomes"]
        )
        for left, right in pairs
    }
    comparisons["C3_to_placebo"] = paired_comparison(
        results["C3"]["outcomes"], placebo["outcomes"]
    )
    return _report(engine, results, placebo, comparisons, other_placebo)


def _report(
    engine: P8Engine,
    results: dict[str, Any],
    placebo: dict[str, Any],
    comparisons: dict[str, Any],
    other_placebo: dict[str, Any],
) -> dict[str, Any]:
    return {
        "contract": "e2-protocol-v2",
        "disclaimer": DISCLAIMER,
        "mode": "scripted_synthetic_only",
        "real_model_requests": 0,
        "professional_corpus_scores": None,
        "actual_v4_runtime": False,
        "questions": 3,
        "option_shuffle": True,
        "repeats": 1,
        "results": results,
        "placebo": placebo,
        "other_year_basis_placebo": other_placebo,
        "paired_comparisons": comparisons,
        "isolated_chart_calculations": len(engine.cache),
        "protocol_stage_calls": sum(
            row["protocol_stage_calls"] for row in results.values()
        )
        + placebo["protocol_stage_calls"]
        + other_placebo["protocol_stage_calls"],
        "engine_provenance": [
            {
                "birth_fingerprint": key,
                "profiles": [
                    {
                        "actual_method": profile["actual_method"],
                        "versions": profile["versions"],
                    }
                    for profile in bundle["profiles"].values()
                ],
            }
            for key, bundle in engine.cache.items()
        ],
        "skill_provenance": _skill("bazi")
        | {"text": "omitted_from_evidence", "context": "omitted_from_evidence"},
        "limits": [
            "只有三道合成时支读数题；C0脚本固定选A，其他脚本读字段，不测试命理推理。",
            "C4仅请求计划与替身回调，不是真实专科Agent或主线合参；未注册任何c#/r#别名。",
            "真实题库未算盘、未打分；只复用先前本机缓存，无新增下载或真实调用。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2 v2 scripted only, no model/network path"
    )
    parser.add_argument("--chart-python", required=True)
    parser.add_argument(
        "--shuffle-options",
        action="store_true",
        default=True,
        help="默认开启；E2 v2固定随机选项，显式传此flag记录同一行为",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_scripted_v2(args.chart_python)
    result["cli_parameters"] = {
        "shuffle_options": args.shuffle_options,
        "shuffle_default": True,
        "year_bases_tested": ["birth_year", "competition_year"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "configurations": list(result["results"]),
                "real_model_requests": 0,
                "protocol_stage_calls": result["protocol_stage_calls"],
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()

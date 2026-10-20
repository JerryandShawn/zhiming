"""Public Brain28 control report contains only source hashes and safe metadata."""

from __future__ import annotations

import json
from typing import Any

from .night24_markdown import _exclusion_tables, _inclusion_tables, _source_tables


def _controls(report: dict[str, Any]) -> list[str]:
    current = report["current_controls"]
    lines = [
        "## 当前控制：宽松安慰剂（同源跨案例）与无盘对照",
        "",
        "按28号M2，固定seed=20261020；捐赠池是本轮2025赛季纳入题所对应的同源案例。",
        "以案例为单位做一对一错配，不同案例且出生不同；同案例的多题、多目标年共享同一捐赠者。",
        "允许捐赠案例原题的目标年不同，原题文字、选项、答案映射与题目目标年保持原样；不跨来源。",
        "实际构建两种对照的输入并检查结构，未送往模型/Agent，未排盘，未评分。结构通过不代表命理能力。",
        "无盘对照仅提供原题与同样重排的选项，不提供源ID、结构化出生资料、盘、技能或规则。",
        "原题文字本身如含出生提示，按裁定保持原题，因此无盘不等于清除了题面所有出生线索。",
        "",
        f"当前状态：{current['status']}；安慰剂构建{current['placebo_inputs_built']}题；"
        f"无盘构建{report['no_chart_control']['inputs_built']}题；推理调用0。",
        "",
        "| 来源 | 题身份SHA256 | 原案例SHA256 | 捐赠案例SHA256 | "
        "原题目标年 | 捐赠案例原题目标年 |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for row in current.get("pairs", []):
        lines.append(
            f"| {row['source']} | `{row['question_identity_sha256']}` | "
            f"`{row['case_identity_sha256']}` | "
            f"`{row['donor_case_identity_sha256']}` | "
            f"{row['question_target_year']} | {row['donor_question_target_years']} |"
        )
    details = {key: value for key, value in current.items() if key != "pairs"}
    return lines + [
        "",
        "```json",
        json.dumps(details, ensure_ascii=False, indent=2),
        "```",
        "",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        report["disclaimer"],
        "",
        "# E2 M2控制脚本演练（2026-10-20，北京时间）",
        "",
        f"本轮{report['counts']['included_questions']}题专业分数和置信区间均为null；"
        "上述40题±15个百分点是旧方案粗略说明，不是本次实测区间。",
        "",
    ]
    for section in (_source_tables, _inclusion_tables, _exclusion_tables, _controls):
        lines.extend(section(report))
        lines.append("")
    lines += [
        "## 历史严格控制与当前界限",
        "",
        "night24原文件不改写。此次另行重跑严格预检仅作历史对照，失败事实仍保留；M2明确授权跨目标年。",
        "```json",
        json.dumps(report["historical_strict_control"], ensure_ascii=False, indent=2),
        "```",
        "",
        "复跑：`python -m mingjing_core.adapters.charts.benchmarks.night28_audit "
        "--mode scripted --mingli-root private/e2-sources/mingli "
        "--baziqa-root private/e2-sources/baziqa "
        "--output docs/v4/evidence/P8/e2-night28-controls-2026-10-20.json`。",
        "",
        "待核：经纬度、历史时区与分钟精度仍需输入预检；本演练不构造未知资料，不证明排盘正确或预测有效。",
        "真实专业题库评分留给主线经用户/大脑另行授权，本分支无真实运行入口。",
        "新下载、服务器请求、模型请求、排盘、专业评分均为0；原文、答案及出生不进入证据。",
    ]
    return "\n".join(lines) + "\n"

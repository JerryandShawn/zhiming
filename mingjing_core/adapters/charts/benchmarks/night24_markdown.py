"""Reviewable tables contain identity hashes and offsets, never source prose."""

from __future__ import annotations

import json
from typing import Any


def _source_tables(report: dict[str, Any]) -> list[str]:
    lines = [
        "## 来源与真实分母",
        "",
        "2025只用于筛选比赛赛季。完整来源与2025子集分别计数，其他赛季不混进本轮排除题数。",
        "文件SHA256绑定本次实际读取内容；commit仅记录缓存仓库HEAD，不冒称工作树已校验干净。",
        "",
        "| 来源 | 全量题数 | 全量结构有效 | 全量年度纳入 | 2025原题 | 2025纳入 | 2025排除 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for source in report["sources"]:
        keys = (
            "full_source_questions",
            "full_schema_valid_questions",
            "full_included_questions",
            "subset_source_questions",
            "subset_included_questions",
            "subset_excluded_questions",
        )
        lines.append(
            "| "
            + source["source"]
            + " | "
            + " | ".join(str(source[k]) for k in keys)
            + " |"
        )
    lines += [
        "",
        "| 来源 | 缓存commit | 文件 | 文件SHA256 | 全量题数 | 2025题数 |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for source in report["sources"]:
        for row in source["files"]:
            lines.append(
                f"| {source['source']} | `{source['source_commit']}` | {row['file']} | "
                f"`{row['source_file_sha256']}` | {row['full_source_questions']} | {row['subset_source_questions']} |"
            )
    return lines


def _inclusion_tables(report: dict[str, Any]) -> list[str]:
    counts = report["counts"]
    lines = [
        "## 逐题纳入清单",
        "",
        f"本次实际纳入{counts['included_questions']}题，**不是40题样本**；没有运行专业题库排盘、Agent或模型，也没有分数。",
        "源公开ID也可能编码出生信息，所以本报告一律只发布题身份/案例SHA256，不复印ID、题面、选项、答案或出生资料。",
        "",
        "| 来源 | 题身份SHA256 | 案例SHA256 | 比赛年 | 题目目标年 | year_basis | reason | 年份字符区间 |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    for row in report["included_audit"]:
        lines.append(
            f"| {row['source']} | `{row['question_identity_sha256']}` | `{row['case_identity_sha256']}` | "
            f"{row['competition_year']} | {row['question_target_year']} | {row['year_basis']} | "
            f"{row['reason']} | {json.dumps(row['evidence_spans'])} |"
        )
    lines += [
        "",
        "字符区间为原题Unicode字符串的零基、左闭右开索引，只定位明确目标年，不包含任何原题片段。",
        f"目标年份集合：{report['target_years']}；目标年等于比赛年2025的题数：{report['target_year_equals_competition_year_count']}。",
        "year_basis固定为question_explicit_target_year，不回退到出生年、比赛年、当前年；有歧义的题保守排除。",
    ]
    return lines


def _exclusion_tables(report: dict[str, Any]) -> list[str]:
    lines = [
        "## 排除理由与逐题记录",
        "",
        "| 原因 | 本2025子集排除题数 |",
        "| --- | ---: |",
    ]
    for reason, count in sorted(report["excluded_reasons"].items()):
        lines.append(f"| {reason} | {count} |")
    missing = report["excluded_reasons"].get("missing_or_invalid_option_labels", 0)
    lines += [
        "",
        f"本2025子集缺标签排除{missing}题；其他赛季的缺标签不进入本分母。缺标签只排除对应问题，不补造标签、答案或整人整文件连坐。",
        f"下表共{report['counts']['excluded_questions']}行，每行代表一条排除记录；原因统计不含其他比赛年份。",
        "",
        "| 来源 | 题身份SHA256 | 排除原因 | year_basis | 年份字符区间 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["excluded_audit"]:
        lines.append(
            f"| {row['source']} | `{row['question_identity_sha256']}` | {row['reason']} | "
            f"null | {json.dumps(row['evidence_spans'])} |"
        )
    return lines


def _placebo(report: dict[str, Any]) -> list[str]:
    preflight = report["placebo_preflight"]
    return [
        "## 打乱生日安慰剂：完整批次预检",
        "",
        "固定seed=20261019，year_basis=question_year，对完整纳入批次恰调用一次same_year_placebo。",
        "要求同一来源、同一题目目标年、不同案例且不同出生记录；一个案例跨多目标年仍须保留同一捐赠者。",
        "不排盘、不打分，重抽0次、跨年兜底0次、跨来源兜底0次；小组可行也不代表完整批次控制可行。",
        "",
        "```json",
        json.dumps(preflight, ensure_ascii=False, indent=2),
        "```",
        "",
        "遇到完整批次不可行即照实拒绝；不能默删题、借其他年份或换seed补齐再冒称原实验。",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        report["disclaimer"],
        "",
        "# E2夜间只读清单与脚本预检（2026-10-19）",
        "",
        "以上±15个百分点仅是原方案对40题量级的粗略说明，**不是本次纳入题数的实测置信区间**。本次专业题库分数和置信区间均为null。",
        f"实际计数与夜间初始14/80、排除66的参考计数一致：{report['reference_counts_match']}。源变化后按实际文件重新计数，不写死分母。",
        "",
    ]
    for section in (_source_tables, _inclusion_tables, _exclusion_tables, _placebo):
        lines.extend(section(report))
        lines.append("")
    lines += ["## 三道合成题脚本流程", ""]
    lines += [
        f"{i}. {step}"
        for i, step in enumerate(report["synthetic_workflow"]["steps"], 1)
    ]
    lines += [
        "",
        "现有入口：`python -m mingjing_core.adapters.charts.benchmarks.scripted_v2 "
        "--chart-python <本机Charts解释器> --shuffle-options --output <合成脚本报告.json>`。",
        "本审计只写明该流程，没有执行合成排盘；该入口仅脚本替身，不是专业题库或真实Agent运行。",
        "C0/C1/C2/C3/C4a/C4b全部已列；历史比赛年控制只作兼容烟测，当前安慰剂以question_year为准。",
        "",
        "## 未完成与待决问题",
        "",
        "完整专业题库安慰剂不可行时，后续实验设计调整交主线和用户在线时决定；本脚本不放宽控制条件。",
        "真实专业题库运行留给主线在用户在线时手动开始；此处没有实现真实provider、Agent、授权或额度路径。",
        "来源经纬度、历史时区与分钟精度仍需实际输入预检；本清单未把数据结构通过等同排盘或预测准确。",
        "本次新下载、服务器请求、模型请求、排盘、专业题库打分均为0。",
    ]
    return "\n".join(lines) + "\n"

"""Contract v2.1 keeps factual checks hard and delegates wording to an independent judge."""

from __future__ import annotations

from typing import Any

from tools.eval.contracts import canonical_hash, scenario_contract_hash
from tools.eval.facts_v21 import LANGUAGE_KEYS, PRIVACY_LITERAL, is_factual
from tools.eval.schema import Expectation, Scenario

VERSION = "deterministic-eval-v2.1.0"
MEANINGS = {
    "must_include_any": "至少表达以下任一含义，接受同义措辞",
    "must_include_all": "表达以下含义，接受同义措辞",
    "must_not_include": "不得肯定以下有害判断；引用、拒绝、否定与纠错不算肯定",
}


def _classify(identity: str, key: str, pattern: str) -> tuple[str, str]:
    if key == "must_not_include" and identity in PRIVACY_LITERAL:
        return "retain_privacy_literal", "删除或锁屏隐私即使否定提及仍会泄露，保留原字面硬检查。"
    if is_factual(pattern):
        return "restore_factual_hard", "事实值使用固定同义格式与否定感知硬检查，不交给评审员自由裁量。"
    return "independent_semantic_judge", "这是措辞或关系含义，接受同义表达；由独立固定评审核对。"


def _language(
    identity: str, index: int, key: str, patterns: list[str]
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    decisions = [_classify(identity, key, pattern) for pattern in patterns]
    mixed = key == "must_include_any" and len({action for action, _ in decisions}) > 1
    hard, semantic, audit = [], [], []
    for pattern, (action, reason) in zip(patterns, decisions, strict=True):
        if mixed:
            action, reason = "independent_semantic_judge", "混合任一组保持原 OR 语义，不擅自收窄。"
        if action == "independent_semantic_judge":
            semantic.append(MEANINGS[key] + "：" + pattern)
        else:
            hard.append(pattern)
        audit.append(
            {"id": identity, "turn": index, "key": key, "patterns": [pattern], "action": action, "reason": reason}
        )
    if key == "must_include_any" and semantic:
        semantic = ["以下为完整的任一组，不是逐项必需：" + "；".join(patterns)]
    return hard, semantic, audit


def migrate(scenario: Scenario) -> tuple[Scenario, list[dict[str, Any]]]:
    converted, audit = scenario.model_copy(deep=True), []
    for index, turn in enumerate(converted.turns, 1):
        data = turn.expect.model_dump(exclude_unset=True)
        semantic = [data.get("judge") or "按用户问题与可核验证据核对回答。"]
        for key in LANGUAGE_KEYS:
            data[key], meanings, rows = _language(scenario.id, index, key, data.get(key, []))
            semantic.extend(meanings)
            audit.extend(rows)
        data["judge"] = "\n".join(semantic)
        if not any(data.get(key) for key in LANGUAGE_KEYS):
            data.setdefault("min_questions", 0)
        turn.expect = Expectation.model_validate(data)
    return converted, audit


def stamp_v2(report: dict[str, Any], scenarios: dict[str, Scenario]) -> None:
    for case in report["cases"]:
        case["scenario_contract_sha256"] = scenario_v21_hash(scenarios[case["id"]])
    report["metadata"].update(
        scoring_contract_version=VERSION,
        scoring_corpus_sha256=canonical_hash(
            {case["id"]: case["scenario_contract_sha256"] for case in report["cases"] if case["status"] != "n/a on v3"}
        ),
    )


def scenario_v21_hash(scenario: Scenario) -> str:
    return canonical_hash({"version": VERSION, "v1_hash_function_on_v21_input": scenario_contract_hash(scenario)})


def audit_markdown(rows: list[dict[str, Any]]) -> str:
    restored = sum(row["action"] == "restore_factual_hard" for row in rows)
    lines = [
        "# 契约 v2.1 逐处断言审计 / Decision Log",
        "",
        "依据 14§C 与 15：确定性事实恢复硬检查，只有措辞交独立评审。",
        "",
        "v1 YAML/rubric/P0 原始报告及旧 c2 报告保持冻结；此表是新的 v2.1 判分口径。",
        f"恢复事实硬检查 {restored} 项；每个模式逐条列出，不按整组关键词一刀切。",
        "日期、星期、农历、节气/节日、天数、热线及固定时间状态使用明确格式同义和否定感知。",
        "隐私禁提词维持字面检查；数据库、工具、回执、问题数量和盘面金标不改。",
        "脚本回放不证明真实模型能力或人工评审一致率。",
        "",
        "| 场景/轮 | 断言 | 原模式 | 决定 | 理由 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        pattern = "；".join(row["patterns"]).replace("|", " / ")
        lines.append(f"| {row['id']}/{row['turn']} | {row['key']} | {pattern} | {row['action']} | {row['reason']} |")
    return "\n".join(lines) + "\n"

"""Independent U12 assertion checker; the earlier six-domain API stays unchanged."""

from __future__ import annotations

import re
from copy import deepcopy

from ..adapters.charts.tool_evidence import evidence_result
from .consistency import _input, _input_aliases, _status
from .consistency_eval import deferred
from .consistency_text import ALIASES, segments
from .consistency_u12_eval import evaluate_u12
from .consistency_u12_input import (
    assessment_facts,
    looks_like_rule,
    masked_labels,
    parse_rule,
)

VERSION = "p8-u12-rule-assertions-preview-v1"
SOURCE = {
    "source_id": "p8-u12-explicit-condition-assertions-v1",
    "title": "P8 U12明确条件断言一致性项目规则",
    "kind": "project_implementation",
    "path": "mingjing_core/skills/consistency_u12.py",
    "locators": [
        "consistency_u12_input.parse_rule",
        "consistency_u12_eval.evaluate_u12",
        "learning_input.verified_input",
    ],
    "support_scope": "只核受信主盘U12 assessment.met，不以同透或候选条件授权完整成格/夺食/制杀效力",
}


def _checks(
    answer: str, chart: dict, facts: list[dict], aliases: dict, documents: dict
) -> list[dict]:
    checks = []
    masked = masked_labels(answer, facts)
    for start, end, _, guard in segments(masked, chart.get("display_name", "")):
        text = answer[start:end]
        if not looks_like_rule(text, facts):
            continue
        query, cited = parse_rule(text, chart.get("display_name", ""))
        if guard:
            row = deferred(guard, field="u12_rule")
        elif any(
            not ALIASES.fullmatch(token) for token in re.findall(r"〔[^〕]*〕", text)
        ):
            row = deferred("citation_syntax_invalid", field="u12_rule")
        else:
            row = evaluate_u12(query, facts, aliases, cited, documents)
        row.update(
            check_id=f"check-{len(checks) + 1}", span={"start": start, "end": end}
        )
        checks.append(row)
    return checks


def _hits(checks: list[dict]) -> list[dict]:
    return [
        {
            "rule_id": "p8.u12_assertions." + row["outcome"],
            "met": True,
            "school": "project-explicit-u12-condition-grammar-v1",
            "source": SOURCE,
            "evidence_paths": [f"/data/checks/{index}"],
            "meaning": "命中的是文本条件比较或保守守卫，不是传统命理成败/效力",
        }
        for index, row in enumerate(checks)
    ]


def check_u12_rule_assertions(
    answer_text: str, chart_compute: dict, *, expected_scope: dict | None = None
) -> dict:
    documents, aliases = _input(answer_text, chart_compute, expected_scope)
    try:
        facts = assessment_facts(chart_compute, documents)
        checks = _checks(answer_text, chart_compute, facts, aliases, documents)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("u12_assertions_chart_fields_invalid") from exc
    data = {
        "status": _status(checks),
        "review_key": "chart_inconsistency",
        "policy": "record_only",
        "text_length": len(answer_text),
        "checks": checks,
        "coverage": {
            "checked": sum(
                row["outcome"] in ("matched", "contradiction") for row in checks
            ),
            "deferred": sum(row["outcome"] == "needs_review" for row in checks),
            "not_checked": sum(row["outcome"] == "not_checked" for row in checks),
        },
        "input_aliases": _input_aliases(chart_compute, checks),
        "input_document_ids": list(documents),
        "input_scope": deepcopy(chart_compute["scope"]),
    }
    result = evidence_result(
        VERSION, data, _hits(checks), [SOURCE], chart_compute["scope"]
    )
    result["limits"] = [
        "独立U12条件断言预览，原六字段check_chart_consistency的v1与旧读者不变；主线须显式分别调用。",
        "有限语法、低召回；同透不是完整夺食/有效制杀，候选命中不是已成格；含糊表达留待复核。",
        "只读受信真太阳主盘实际assessments；true须与同盘hit完整一致，false无传统r且仍须真实c。",
        "顶层c/r仅本结果比较规则；data.input_aliases/input_citations是原盘命名空间，短名不能混用。",
        "内容hash不是签名或授权；调用方须验证provider、owner、revision/撤销，expected_scope只作严格上下文比较。",
        "不回显原文，不调用模型/网络/数据库，不自动改答案；主线Registry/review接入尚未完成。",
    ]
    return result

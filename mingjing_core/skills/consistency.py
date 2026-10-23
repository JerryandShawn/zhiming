"""High-precision, low-recall chart contradiction preview for mainline review #15."""

from __future__ import annotations

import re
from copy import deepcopy

from ..adapters.charts.tool_evidence import evidence_result
from .consistency_eval import deferred, evaluate
from .consistency_facts import primary_facts
from .consistency_text import ALIASES, TOPIC, parse_clause, segments
from .learning_input import verified_input

VERSION = "p8-chart-consistency-preview-v1"
SOURCE = {
    "source_id": "p8-explicit-text-consistency-v1",
    "title": "P8明确文本断言一致性项目规则",
    "kind": "project_implementation",
    "path": "mingjing_core/skills/consistency.py",
    "locators": [
        "consistency_text.parse_clause",
        "consistency_eval.evaluate",
        "learning_input.verified_input",
    ],
    "support_scope": "只核白名单断言与受信计算事实是否一致；不证明命理效度或完整语义理解",
}


def _input(answer: str, chart: dict, expected_scope: dict | None) -> tuple[dict, dict]:
    if not isinstance(answer, str) or len(answer) > 32000:
        raise ValueError("consistency_answer_invalid")
    try:
        documents, aliases = verified_input(chart)
    except (ValueError, TypeError) as exc:
        raise ValueError("consistency_chart_invalid") from exc
    if expected_scope is not None and (
        not isinstance(expected_scope, dict)
        or set(expected_scope) != set(chart["scope"])
        or any(
            type(expected_scope[key]) is not type(item) or expected_scope[key] != item
            for key, item in chart["scope"].items()
        )
    ):
        raise ValueError("consistency_scope_mismatch")
    return documents, aliases


def _checks(answer: str, chart: dict, facts: list[dict], aliases: dict) -> list[dict]:
    checks = []
    for start, end, text, guard in segments(answer, chart.get("display_name", "")):
        if not TOPIC.search(text):
            continue
        query, cited = parse_clause(text, chart.get("display_name", ""))
        if guard:
            check = deferred(guard)
        elif any(
            not ALIASES.fullmatch(token) for token in re.findall(r"〔[^〕]*〕", text)
        ):
            check = deferred("citation_syntax_invalid")
        elif query is None:
            check = deferred("unsupported_grammar", outcome="not_checked")
        else:
            check = evaluate(query, facts, aliases, cited)
        check.update(
            check_id=f"check-{len(checks) + 1}", span={"start": start, "end": end}
        )
        checks.append(check)
    return checks


def _status(checks: list[dict]) -> str:
    outcomes = {row["outcome"] for row in checks}
    if "contradiction" in outcomes:
        return "inconsistent"
    if "needs_review" in outcomes:
        return "needs_review"
    if "matched" in outcomes:
        return "no_contradiction_found"
    return "not_checked"


def _rule_hits(checks: list[dict]) -> list[dict]:
    return [
        {
            "rule_id": "p8.consistency."
            + (row["field"] or "context_guard")
            + "."
            + row["outcome"],
            "met": True,
            "school": "project-explicit-text-grammar-v1",
            "source": SOURCE,
            "evidence_paths": [f"/data/checks/{index}"],
            "meaning": "命中的是文本比较或保守守卫规则，不是命理格局/用神成立",
        }
        for index, row in enumerate(checks)
    ]


def _input_aliases(chart: dict, checks: list[dict]) -> dict:
    names = {
        name
        for row in checks
        for field in ("input_c_aliases", "input_r_aliases")
        for name in row[field]
    }
    for row in chart["aliases"]["r"]:
        if row["alias"] in names:
            names.update(row["evidence_aliases"])
    return {
        key: [deepcopy(row) for row in chart["aliases"][key] if row["alias"] in names]
        for key in ("c", "r")
    }


def check_chart_consistency(
    answer_text: str, chart_compute: dict, *, expected_scope: dict | None = None
) -> dict:
    documents, aliases = _input(answer_text, chart_compute, expected_scope)
    try:
        facts = primary_facts(chart_compute, documents)
        checks = _checks(answer_text, chart_compute, facts, aliases)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("consistency_chart_fields_invalid") from exc
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
        VERSION, data, _rule_hits(checks), [SOURCE], chart_compute["scope"]
    )
    result["limits"] = [
        "有限中文白名单语法，精度优先、召回有限；no_contradiction_found不等于全文已核或正确。",
        "格局筛选/三法用神都保留候选属性；已成格/用神已定、引用、假设、疑问、比较口径须人工复核。",
        "输入hash只校验内容不是签名，主线须验证provider、owner、修订与撤销；expected_scope只是可选上下文比较。",
        "顶层c/r仅本结果比较规则命名空间；data.input_aliases/input_citations是原盘命名空间，不能混用短名。",
        "不回显正文、不发模型、不自动阻断/改写；主线review #15仍须独立授权与集成验收。",
    ]
    return result

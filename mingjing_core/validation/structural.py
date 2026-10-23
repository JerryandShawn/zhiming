"""Fail-open deterministic checks, independent from runtime, model and storage services."""

import re

from .structural_contracts import StructuralContext, StructuralFinding, StructuralResult
from .structural_dates import check_relative_dates, fix_weekdays
from .structural_receipts import annotate_receipts, remove_unknown_aliases

FALLBACK_TEXT = "我这会儿没能把回答整理好。你可以再说一句，我会接着帮你。"


def _farewell(text: str, context: StructuralContext) -> tuple[str, list[StructuralFinding]]:
    if not context.farewell:
        return text, []
    parts = re.split(r"(\n\s*\n)", text)
    last_index = next((index for index in range(len(parts) - 1, -1, -1) if parts[index].strip()), None)
    if last_index is None:
        return text, []
    last = parts[last_index]
    sentences = re.findall(r"[^。！？!?\n]+[。！？!?]?|\n", last)
    if not any("？" in sentence or "?" in sentence for sentence in sentences):
        return text, []
    parts[last_index] = "".join(sentence for sentence in sentences if "？" not in sentence and "?" not in sentence)
    updated = "".join(parts)
    finding = StructuralFinding("farewell_question_removed", None, 2, last, "告别轮不追加问题")
    return updated if updated.strip() else text, [finding]


def structural_check(text: str, context: StructuralContext) -> StructuralResult:
    original = text if isinstance(text, str) else ""
    current = original
    findings: list[StructuralFinding] = []
    try:
        if not current.strip():
            current = context.last_model_text if context.last_model_text.strip() else FALLBACK_TEXT
            findings.append(StructuralFinding("empty_answer", None, 3, "", "空回答使用最后文本或友好说明兜底"))
        if type(context.ask_user_calls) is not int or context.ask_user_calls < 0:
            raise ValueError("提问计数无效")
        for check in (remove_unknown_aliases, annotate_receipts, fix_weekdays, check_relative_dates, _farewell):
            current, new_findings = check(current, context)
            findings.extend(new_findings)
        if context.ask_user_calls > 1:
            findings.append(StructuralFinding("ask_user_limit", None, 3, "", "每轮最多一次ask_user"))
        if not current.strip():
            current = FALLBACK_TEXT
            findings.append(StructuralFinding("empty_answer", None, 3, "", "清理引用后为空，使用友好说明兜底"))
        return StructuralResult(current, tuple(findings), context.ask_user_calls < 1)
    except Exception:
        findings.append(StructuralFinding("structural_internal_error", None, 2, "", "结构检查出错但仍交付回答"))
        return StructuralResult(
            current if current.strip() else original if original.strip() else FALLBACK_TEXT, tuple(findings), False
        )

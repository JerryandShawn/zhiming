"""Resolve only this run's citations and qualify unsupported persistence claims."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mingjing_core.domain.contracts import EvidenceError

ALIAS = re.compile(r"〔([A-Za-z][A-Za-z0-9_:-]{0,100})〕")
SAVE_CLAIM = re.compile(
    r"(?<!还没)(?<!尚未)(?<!没有)(?<!未)(?<!没)(?:我(?:已经|已)?记下了|已记住|已经记住|已保存|已经保存)"
)
SAVE_KINDS = frozenset({"fact", "note", "reminder", "followup", "case", "feedback"})
ANNOTATION = "（这条还没有真正保存，需要的话告诉我）"
EMPTY_ANSWER = "这次还没整理出完整回答，请稍后继续。"


def _has_save_annotation(text: str, match: re.Match[str]) -> bool:
    tail = text[match.end() :]
    if tail.startswith(ANNOTATION):
        return True
    target, found, _ = tail.partition(ANNOTATION)
    if not found or not target or target[-1].isspace():
        return False
    punctuation = "，,。！？!?；;\n"
    clause = target[:-1] if target[-1] in punctuation else target
    # P6 annotates the complete clause. A note in another clause, quotation,
    # or near-matching wording cannot excuse this persistence assertion.
    return not any(character in punctuation + "“”‘’\"'（）()" for character in clause)


@dataclass(frozen=True)
class StructuralResult:
    text: str
    used_fact_ids: tuple[str, ...]
    used_claim_ids: tuple[str, ...]
    cited_keys: tuple[str, ...]
    warnings: tuple[dict[str, str | int], ...] = field(repr=False)


def check_structure(
    text: str,
    alias_map: dict[str, dict[str, Any]],
    receipts: tuple[dict[str, Any], ...] = (),
    *,
    fallback: str = EMPTY_ANSWER,
) -> StructuralResult:
    if not isinstance(text, str) or len(text) > 200_000:
        raise EvidenceError("回答格式或长度无效")
    facts: list[str] = []
    claims: list[str] = []
    keys: list[str] = []
    unknown = 0

    def resolve(match: re.Match[str]) -> str:
        nonlocal unknown
        value = alias_map.get(match.group(1))
        if not isinstance(value, dict):
            unknown += 1
            return ""
        kind, ident, revision = (value.get(key) for key in ("kind", "id", "revision"))
        if not isinstance(kind, str) or not isinstance(ident, str) or type(revision) is not int or revision < 1:
            raise EvidenceError("本轮引用映射无效")
        keys.append(kind + ":" + ident)
        if kind == "fact":
            facts.append(ident)
        if kind == "interpretive_claim":
            claims.append(ident)
        return match.group()

    checked = ALIAS.sub(resolve, text).strip() or fallback
    warnings: list[dict[str, str | int]] = []
    if unknown:
        warnings.append({"code": "unknown_alias_removed", "count": unknown})
    saved = any(item.get("write_status") == "saved" and item.get("kind") in SAVE_KINDS for item in receipts)
    if not saved and SAVE_CLAIM.search(checked):
        checked = SAVE_CLAIM.sub(
            lambda match: match.group() if _has_save_annotation(checked, match) else match.group() + ANNOTATION,
            checked,
        )
        warnings.append({"code": "unsupported_save_claim", "count": 1})
    if not text.strip():
        warnings.append({"code": "empty_answer_fallback", "count": 1})
    return StructuralResult(
        checked,
        tuple(dict.fromkeys(facts)),
        tuple(dict.fromkeys(claims)),
        tuple(dict.fromkeys(keys)),
        tuple(warnings),
    )

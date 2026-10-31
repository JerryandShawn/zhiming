"""A small assertion grammar; only a corresponding successful receipt can authorise it."""

import re
from collections.abc import Mapping
from typing import Any

from .structural_contracts import StructuralContext, StructuralFinding

SAVE_NOTE = "（这条还没有真正保存，需要的话告诉我）"
ALIAS_PATTERN = re.compile(r"〔([A-Za-z][A-Za-z0-9_-]{0,63})〕")
SAVE_PATTERNS = (
    re.compile(r"(?:已(?:经)?|已经)(?:帮你|替你|给你)?(?:记下|记住|保存|更新)(?:了|好|完成)?"),
    re.compile(r"(?:我|帮你|替你|给你)(?:记下|记住|保存|更新)(?:了|好了)"),
    re.compile(r"(?:保存|更新|记录|记忆)(?:好|完成)了"),
)
NEGATED = re.compile(r"(?:没有|还没(?:有)?|尚未|不会|不要|不再|不是|未|不).{0,4}$")
CLAUSE_PATTERN = re.compile(r"[^，,。！？!?；;\n]+[，,。！？!?；;]?|\n")


def remove_unknown_aliases(text: str, context: StructuralContext) -> tuple[str, list[StructuralFinding]]:
    findings = []

    def substitute(match: re.Match[str]) -> str:
        if match.group(1) in context.aliases:
            return match.group(0)
        findings.append(StructuralFinding("unknown_alias", None, 2, match.group(0), "移除本轮没有提供的引用"))
        return ""

    return ALIAS_PATTERN.sub(substitute, text), findings


def _normalise(value: str) -> str:
    return re.sub(r"[\s，,。！？!?；;：:〔〕]", "", value).casefold()


def _success(receipt: Mapping[str, Any]) -> bool:
    if not isinstance(receipt, Mapping):
        return False
    if "status" in receipt and "write_status" in receipt and receipt["status"] != receipt["write_status"]:
        return False
    status = receipt.get("write_status", receipt.get("status"))
    return isinstance(status, str) and status in {"saved", "updated"}


def _assertions(clause: str) -> list[re.Match[str]]:
    assertions = []
    for pattern in SAVE_PATTERNS:
        for match in pattern.finditer(clause):
            prefix = clause[max(0, match.start() - 16) : match.start()]
            local = re.split(r"但是|然而|而现在|但现在|不过|现在|这次|但|：|:", prefix)[-1]
            if not NEGATED.search(local):
                assertions.append(match)
    return assertions


def _corresponds(clause: str, assertion: re.Match[str], receipt: Mapping[str, Any], context: StructuralContext) -> bool:
    if not _success(receipt):
        return False
    target = re.split(r"[（(]", clause[assertion.end() :], maxsplit=1)[0]
    target_aliases = set(ALIAS_PATTERN.findall(target))
    plain_target = _normalise(ALIAS_PATTERN.sub("", target))
    summary = receipt.get("summary")
    # The caller must derive this target projection from a real receipt, never from a model assertion.
    if isinstance(summary, str) and len(_normalise(summary)) >= 4 and _normalise(summary) == plain_target:
        return True
    alias = receipt.get("alias")
    prefix = clause[: assertion.start()].strip()
    return (
        isinstance(alias, str)
        and alias in context.aliases
        and alias in target_aliases
        and not plain_target
        and prefix in {"", "我", "这条", "内容", "这项偏好", "你的偏好"}
    )


def annotate_receipts(text: str, context: StructuralContext) -> tuple[str, list[StructuralFinding]]:
    findings = []

    def substitute(match: re.Match[str]) -> str:
        clause = match.group(0)
        asserted = _assertions(clause)
        if not asserted or clause.endswith(("？", "?")):
            return clause
        if all(
            any(_corresponds(clause, assertion, receipt, context) for receipt in context.receipts)
            for assertion in asserted
        ):
            return clause
        findings.append(
            StructuralFinding(
                "false_receipt",
                "E2",
                5,
                clause,
                "保存或更新必须有对应成功回执",
                "receipts:missing_corresponding_success",
                "补真正回执或撤销保存断言",
            )
        )
        return clause if text[match.end() :].startswith(SAVE_NOTE) else clause + SAVE_NOTE

    return CLAUSE_PATTERN.sub(substitute, text), findings

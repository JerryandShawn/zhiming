"""Pure review routing: no provider access, user text retention, or calibration activation."""

from dataclasses import dataclass
import re
from typing import Literal

ReviewMode = Literal["risk", "always", "off"]
CHART = re.compile(
    r"〔[cr][1-9]\d*〕|\[[cr][1-9]\d*\]|命盘|排盘|八字|紫微|日主|喜用|流年|星盘"
)
DATE = re.compile(
    r"(?<!\d)(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}月\d{1,2}[日号])(?!\d)"
)
MEMORY = re.compile(
    r"我(?:已经|已)?(?:帮你)?(?:记下|记住|保存)|已保存|你(?:上次|之前)(?:说|提到)|(?:记得|根据)(?:你|上次).{0,12}(?:说|提到|记忆)"
)
SENSITIVE = re.compile(
    r"诊断|病情|用药|停药|就医|药物|血压|检查结果|起诉|诉讼|法律|律师|合同|维权|投资|股票|证券|基金(?!会)|杠杆|仓位|收益率"
)


@dataclass(frozen=True)
class ReviewRisk:
    should_review: bool
    reasons: tuple[str, ...]


def assess_review_risk(
    draft: str,
    *,
    mode: ReviewMode = "risk",
    chart_or_evidence: bool = False,
    memory_reference: bool = False,
    decision_card: bool = False,
) -> ReviewRisk:
    """Route substantive risk only; unavailable calibration still stays record_only elsewhere."""
    if not isinstance(draft, str) or mode not in {"risk", "always", "off"}:
        raise ValueError("review routing requires text and an explicit known mode")
    if any(
        type(flag) is not bool
        for flag in (chart_or_evidence, memory_reference, decision_card)
    ):
        raise ValueError("review context flags must be actual booleans")
    if mode == "off":
        return ReviewRisk(False, ("off",))
    if mode == "always":
        return ReviewRisk(True, ("always",))
    conditions = (
        (chart_or_evidence or bool(CHART.search(draft)), "chart_or_evidence"),
        (bool(DATE.search(draft)), "concrete_date"),
        (memory_reference or bool(MEMORY.search(draft)), "memory"),
        (bool(SENSITIVE.search(draft)), "health_legal_investment"),
        (decision_card, "decision_card"),
        (len(draft) > 400, "long_answer"),
    )
    reasons = tuple(reason for hit, reason in conditions if hit)
    return ReviewRisk(bool(reasons), reasons)

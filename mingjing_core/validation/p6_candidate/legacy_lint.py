"""The complete v3 rules produce warnings; they never revise or gate delivery.

The caller supplies the rendered answer (including appendix) and the released
snapshot. No repository, model, clock, or network is accessed here. Existing v3
entry points are untouched. Source: consultation.py:545-944, SHA256 below.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from mingjing_core.domain.consultation import FinalAnswer

from .legacy_decisions import completion_issues, decision_issues
from .legacy_guarantees import guarantee_issues
from .legacy_save import save_issues
from .legacy_symbolic import symbolic_issues

V3_SOURCE_SHA256 = "1a041a66ff95bc50fd5e1bf9642c95e34bfc0386ac4e03baf2c9709cbb365fdb"

# Severity is advisory metadata for migrated rules, never a revision decision.
# Original v3 only returned these messages; it supplied neither severity nor span.
RULES: dict[str, tuple[str, int]] = {
    "声明的字段、规则、流派或解释范围重验失败": ("legacy_claim_revalidation", 4),
    "引用了本轮有效范围之外的事实": ("legacy_unknown_fact_reference", 4),
    "引用了未通过规则核验的声明": ("legacy_unknown_claim_reference", 4),
    "保存或删除提示必须由实际程序回执生成": ("legacy_unsupported_receipt", 5),
    "象征解释被提升为现实确定性或概率": ("legacy_symbolic_certainty", 4),
    "现实决策缺少选择代价或行动": ("legacy_decision_missing_actions", 3),
    "现实决策需要至少两个可行选择，可包含暂缓与核实": ("legacy_decision_missing_options", 3),
    "已有现实资料时，决策必须引用本轮有效事实依据": ("legacy_decision_missing_fact_citation", 3),
    "用户明确不能上夜班，未授权修改时不能建议少量例外或次数放宽": ("legacy_night_constraint", 4),
    "熟悉关系、流程或协商成本低没有已授权现实来源，不可作为推荐理由": ("legacy_unsupported_familiarity", 4),
    "费用、退出和风险条件未经确认，不能承诺完全可逆或无损失": ("legacy_unsupported_reversibility", 3),
    "支持模式只给最多一个低负担行动": ("legacy_support_action_overload", 2),
    "专业结果缺少经过核验的声明引用": ("legacy_missing_claim_citation", 4),
}


class Revalidator(Protocol):
    def __call__(
        self, calculation: dict[str, Any], claims: list[dict[str, Any]], tarot_provenance: Any
    ) -> dict[str, Any]:
        "Validate released claim metadata using a caller-owned pure dependency."
        ...


@dataclass(frozen=True)
class LintContext:
    snapshot: dict[str, Any] = field(repr=False)
    calculation: dict[str, Any] = field(repr=False)
    plan: dict[str, Any] = field(repr=False)
    run_request: dict[str, Any] = field(repr=False)
    final_answer: dict[str, Any] | None = field(default=None, repr=False)
    revalidator: Revalidator | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: int
    span: tuple[int, int] | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "severity": self.severity, "span": self.span, "message": self.message}


def _final_answer(text: str, context: LintContext) -> dict[str, Any]:
    if context.final_answer is not None:
        return deepcopy(context.final_answer)
    return {
        "plain_summary": text,
        "explanation": "",
        "actions": [],
        "decision_options": [],
        "follow_up": "",
        "professional_appendix": "",
        "cited_fact_ids": [],
        "cited_claim_ids": [],
        "caveats": [],
    }


def _messages(text: str, final: dict[str, Any], context: LintContext) -> list[str]:
    snap = deepcopy(context.snapshot)
    facts = {fact["id"]: fact for fact in snap["facts"]}
    calculation = deepcopy(context.calculation)
    claims = {claim["claim_id"]: claim for claim in calculation["claims"]}
    issues = []
    if context.revalidator is not None:
        checked = context.revalidator(
            calculation["calculation"], calculation["claims"], calculation.get("tarot_provenance")
        )
        if not checked["eligible"]:
            issues.append("声明的字段、规则、流派或解释范围重验失败")
    if set(final["cited_fact_ids"]) - set(facts):
        issues.append("引用了本轮有效范围之外的事实")
    if set(final["cited_claim_ids"]) - set(claims):
        issues.append("引用了未通过规则核验的声明")
    issues.extend(save_issues(text))
    issues.extend(symbolic_issues(text))
    plan = deepcopy(context.plan)
    decision, factual = decision_issues(text, final, facts, claims, plan, deepcopy(context.run_request))
    issues.extend(decision)
    issues.extend(guarantee_issues(text, factual))
    issues.extend(completion_issues(final, claims, plan))
    return issues


def lint(text: str, context: LintContext) -> list[Finding]:
    """Return controlled warning metadata; no private text enters error messages.

    Spans are null because the inherited aggregate rules did not identify one
    exact location. Claim revalidation must be injected when claims are present;
    its absence is observable rather than treated as successful verification.
    """
    try:
        if not isinstance(text, str) or not isinstance(context, LintContext):
            raise TypeError("invalid lint input")
        final = _final_answer(text, context)
        FinalAnswer.model_validate(final)
        messages = _messages(text, final, context)
        findings = [Finding(RULES[message][0], RULES[message][1], None, message) for message in messages]
        if context.revalidator is None and context.calculation.get("claims"):
            findings.append(Finding("legacy_revalidation_unavailable", 1, None, "未提供声明重验结果，仅记录告警"))
        return findings
    except ValidationError:
        return [Finding("lint_schema_error", 1, None, "旧版结构契约未通过，回答仍可交付")]
    except Exception:
        return [Finding("lint_internal_error", 1, None, "旧版告警检查未完成，回答仍可交付")]

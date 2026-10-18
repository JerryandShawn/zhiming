"""Every original warning and finite denial family is checked against the v3 oracle."""

import ast
import json
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.validation.legacy_lint import RULES, Finding, lint
from tests.v4.validation.legacy_support_mod import context, final_answer, original_warnings, rendered

TEXT_CASES = [
    "我已经为你保存到长期记忆。",
    "我会记住。",
    "已经删除记忆。",
    "不声称已保存或更新任何资料。",
    "不包含任何“已记住/已保存/已更新/已删除”状态的声称。",
    "不是不包含任何“已记住/已保存/已更新/已删除”状态的声称。",
    "不声称已保存。但我已经保存了。",
    "不能声称已保存，不过我会记住。",
    "不是不声称已保存。",
    "并非不能声称已经保存。",
    "牌面保证成功。",
    "命盘证明结果。",
    "八字成功率80%。",
    "星盘一定会带来成功。",
    "八字不构成对学习效果、成绩的任何保证。",
    "八字并非不构成学习效果保证。",
    "八字不会不构成学习效果保证。",
    "牌面不产生任何概率或吉凶保证。",
    "不是牌面不产生任何概率或吉凶保证。",
    "不能把牌面当作结果的证明。",
    "不能把牌面当作结果的证明，也不能给出成败概率。",
    "不是不能把牌面当作结果的证明。",
    "“不能把牌面当作结果的证明”。",
    "没有任何牌面或算法能证明结果。",
    "没有任何牌面或算法能证明结果，但这次一定会成功。",
    "并非没有任何牌面能证明结果。",
    "不能由牌面保证。",
    "不是不能由牌面保证。",
    "不由牌面证明。",
    "不是不由牌面证明。",
    "八字仅采用正午快照，未证明整日不换日柱。",
    "八字仅采用正午快照，未证明整日不换日柱，但可以保证结果。",
    "不能摘取单一相位证明结果。",
    "不建议少量夜班。",
    "不是不建议少量夜班。",
    "不建议夜班例外，但可以接受该安排。",
    "不能上夜班，不设例外。",
    "今天向A发出班次与夜班例外书面问题。不能上夜班。",
    "在收到A书面班次/夜班例外答复后复盘。不接受夜班。",
    "A班次、夜班例外、轮班/顶班、报名截止与退出条件未知。不排夜班。",
    "可以每周接受一次夜班。",
    "流程已经熟悉，可以直接选择。",
    "协商成本低。",
    "这个选择零风险。",
    "不能承诺零风险。",
    "不能承诺零风险，但选择B零风险。",
    "并非不能保证零风险。",
    "不作零风险、完全可逆的保证。",
    "不能按“零风险或完全可逆”处理。",
    "非推断为零风险、完全可逆。",
    "未作任何零风险、完全可逆的推断。",
    "不是未作任何零风险、完全可逆的推断。",
    "“未作任何零风险的推断”。",
    "不把未知退出条件解释为无损失退出。",
    "“不把未知退出条件解释为无损失退出”。",
    "不能认定选择B可无损失退出。",
    "不是：不能认定选择B可无损失退出。",
    "若B费用不可接受能否无损失退出，取决于B的退出条件，待核实。",
    "因此不存在零成本、零风险或完全可逆的路径。",
    "未对任何费用、退出或可逆性做零成本、完全可逆或无损失的假设。",
    "费用未知，不能假设费用可接受或退出无损失。",
    "退出是否零损失也取决于尚未确认的具体条款。",
    "能否零风险尚未确认。",
    "零风险的说法没有依据。",
    "上一轮写的“零风险”属于过度承诺。",
    "不是撤回“零风险”。",
    "撤回“零风险”。",
    "已经修正上一轮过度承诺，删除了“零风险”。",
    "已经修正上一轮过度承诺，但不是删除了“零风险”。",
    "此前将“询问”表述为零风险、未强调损失可能，现已在各选项的reversibility字段中明确——退出条件、费用和风险条件均未经确认。",
    "上一轮将“暂缓决定”描述为“完全可逆”，本轮已更正为“不产生付款承诺但消耗不可收回的时间与机会成本，不能视为零成本或完全无损失”。",
    "已将decision_options中所有reversibility表述从“零风险”修正为“可停止但已投入时间不可收回、承诺后可逆性取决于未知退出条件”。",
]


@pytest.mark.parametrize("text", TEXT_CASES, ids=[f"synthetic-rule-{i:03}" for i in range(len(TEXT_CASES))])
def test_copied_text_rules_exactly_match_original(text: str) -> None:
    final = final_answer(text)
    ctx = context(final)
    assert [finding.message for finding in lint(rendered(final), ctx)] == original_warnings(final, ctx)


@pytest.mark.parametrize("message,rule", [(message, value[0]) for message, value in RULES.items()])
def test_all_thirteen_original_rule_categories_are_reachable(message: str, rule: str) -> None:
    final, ctx = _case_for(rule)
    expected = original_warnings(final, ctx)
    findings = lint(rendered(final), ctx)
    assert message in expected
    assert [finding.message for finding in findings] == expected
    assert any(finding.rule == rule and 1 <= finding.severity <= 5 for finding in findings)


def _case_for(rule: str) -> tuple[dict[str, Any], Any]:
    final = final_answer()
    ctx = context(final)
    if rule == "legacy_claim_revalidation":
        ctx = replace(ctx, revalidator=lambda *args: {"eligible": False})
    elif rule == "legacy_unknown_fact_reference":
        final["cited_fact_ids"] = ["missing"]
    elif rule == "legacy_unknown_claim_reference":
        final["cited_claim_ids"] = ["missing"]
    elif rule == "legacy_unsupported_receipt":
        final["plain_summary"] = "我已经保存到记忆。"
    elif rule == "legacy_symbolic_certainty":
        final["plain_summary"] = "牌面保证成功。"
    elif rule.startswith("legacy_decision_"):
        ctx.plan["decision"] = True
    elif rule == "legacy_night_constraint":
        final["plain_summary"] = "建议尝试少量夜班。"
    elif rule == "legacy_unsupported_familiarity":
        final["plain_summary"] = "流程已经熟悉。"
    elif rule == "legacy_unsupported_reversibility":
        final["plain_summary"] = "这条路径零风险。"
    elif rule == "legacy_support_action_overload":
        ctx.plan["mode"] = "support"
        final["actions"] = ["第一项小行动", "第二项小行动"]
    elif rule == "legacy_missing_claim_citation":
        ctx.plan["systems"] = ["bazi"]
    return final, ctx


@pytest.mark.parametrize("field", ["plain_summary", "explanation", "follow_up", "professional_appendix", "caveats"])
def test_all_rendered_fields_keep_the_same_v3_detection(field: str) -> None:
    final = final_answer()
    final[field] = ["我已经保存到记忆。"] if field == "caveats" else "我已经保存到记忆。"
    ctx = context(final)
    assert [finding.message for finding in lint(rendered(final), ctx)] == original_warnings(final, ctx)


@pytest.mark.parametrize("kind", ["confirmed", "hypothesis", "hearsay", "concern", "context_only"])
@pytest.mark.parametrize(
    "fact_text", ["这个选择零风险", "不能保证零风险", "能否零风险？", "已撤回零风险", "随时可退款"]
)
def test_guarantee_source_evidence_keeps_original_filters(kind: str, fact_text: str) -> None:
    final = final_answer("这个选择零风险。")
    ctx = context(final)
    ctx.snapshot["facts"] = [{"id": "f1", "content": fact_text, "kind": kind, "context_only": kind == "context_only"}]
    assert [finding.message for finding in lint(rendered(final), ctx)] == original_warnings(final, ctx)


def test_warning_order_and_delivery_are_unchanged_when_many_rules_fire() -> None:
    final = final_answer("我已经保存到记忆。牌面保证成功。建议尝试少量夜班。流程已经熟悉。这条路径零风险。")
    final["actions"] = ["行动一", "行动二"]
    final["cited_claim_ids"] = ["unknown"]
    ctx = context(final)
    ctx.plan.update(decision=True, mode="support", systems=["bazi"])
    before = deepcopy(final)
    warnings = lint(rendered(final), ctx)
    assert [finding.message for finding in warnings] == original_warnings(final, ctx)
    assert len(warnings) >= 9
    assert final == before


def test_schema_failure_is_only_a_fixed_warning_without_private_content() -> None:
    final = final_answer("synthetic-private-marker")
    final["actions"] = "synthetic-private-marker"
    findings = lint("synthetic-private-marker", context(final))
    assert findings == [Finding("lint_schema_error", 1, None, "旧版结构契约未通过，回答仍可交付")]
    assert "synthetic-private-marker" not in json.dumps([item.as_dict() for item in findings])


def test_internal_exception_is_not_a_delivery_exception_or_private_diagnostic() -> None:
    def broken(*args: Any) -> dict[str, Any]:
        raise RuntimeError("synthetic-private-marker")

    final = final_answer()
    findings = lint(rendered(final), replace(context(final), revalidator=broken))
    assert len(findings) == 1 and findings[0].rule == "lint_internal_error"
    assert "synthetic-private-marker" not in json.dumps(findings[0].as_dict())


def test_revalidator_receives_copies_and_missing_dependency_is_visible() -> None:
    def mutating(calculation: dict[str, Any], claims: list[dict[str, Any]], provenance: Any) -> dict[str, Any]:
        claims.clear()
        calculation["mutated"] = True
        return {"eligible": True}

    final = final_answer()
    ctx = replace(context(final), revalidator=mutating)
    before = deepcopy(ctx.calculation)
    assert lint(rendered(final), ctx) == []
    assert ctx.calculation == before
    assert lint(rendered(final), replace(ctx, revalidator=None))[-1].rule == "legacy_revalidation_unavailable"


def test_runtime_lint_does_not_delegate_to_old_validator(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("v3 runtime delegation is forbidden")

    monkeypatch.setattr(ConsultationService, "_validate", forbidden)
    final = final_answer("我已经保存到记忆。")
    findings = lint(rendered(final), context(final))
    assert findings[0].rule == "legacy_unsupported_receipt"


def test_every_original_regex_literal_value_is_present_in_copied_modules() -> None:
    source = Path("mingjing_core/application/consultation.py").read_text(encoding="utf-8")
    original = next(
        node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == "_validate"
    )
    expected = Counter(
        node.value
        for node in ast.walk(original)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(char in node.value for char in r"\^$[](){}|.?*+")
    )
    copied: Counter[str] = Counter()
    for path in Path("mingjing_core/validation").glob("legacy_*.py"):
        copied.update(
            node.value
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
    assert len(expected) >= 75
    assert not expected - copied

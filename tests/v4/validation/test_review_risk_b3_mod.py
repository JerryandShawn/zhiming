"""Synthetic positive/negative routing cases; no model calls or quality claims."""

import pytest

from mingjing_core.validation.review_risk import assess_review_risk

POSITIVE = [
    ("甲木日主〔c3〕", {}, "chart_or_evidence"),
    ("可参考[r2]。", {}, "chart_or_evidence"),
    ("这份星盘只作参考。", {}, "chart_or_evidence"),
    ("约在2026-10-27。", {}, "concrete_date"),
    ("安排在10月21日。", {}, "concrete_date"),
    ("截止2026/11/2。", {}, "concrete_date"),
    ("我已经帮你记下了。", {}, "memory"),
    ("已保存这个偏好。", {}, "memory"),
    ("你上次提到准备面试。", {}, "memory"),
    ("用药应与医生讨论。", {}, "health_legal_investment"),
    ("检查结果需要专业解释。", {}, "health_legal_investment"),
    ("请让律师核对合同。", {}, "health_legal_investment"),
    ("这涉及投资风险。", {}, "health_legal_investment"),
    ("不要据此调整股票仓位。", {}, "health_legal_investment"),
    ("合成" * 201, {}, "long_answer"),
    ("这是一个简短回答。", {"decision_card": True}, "decision_card"),
    ("这是一个简短回答。", {"memory_reference": True}, "memory"),
    ("这是一个简短回答。", {"chart_or_evidence": True}, "chart_or_evidence"),
]
NEGATIVE = [
    "你好。",
    "再见，今天先聊到这里。",
    "谢谢你告诉我。",
    "可以慢慢想。",
    "祝你健康快乐。",
    "这家基金会提供公益服务。",
    "你想喝茶还是咖啡？",
    "版本2.1.0已经发布。",
    "预算约400元。",
    "每周散步三次也不错。",
    "先列出你最看重的两点。",
    "保持自己的判断。",
    "今天心情如何？",
    "我的记忆力一般。",
    "字" * 400,
]


@pytest.mark.parametrize("draft,flags,reason", POSITIVE)
def test_each_explicit_risk_condition_routes_review(draft, flags, reason):
    result = assess_review_risk(draft, **flags)
    assert result.should_review and reason in result.reasons


@pytest.mark.parametrize("draft", NEGATIVE)
def test_low_risk_replies_do_not_route_review(draft):
    result = assess_review_risk(draft)
    assert not result.should_review and result.reasons == ()


def test_off_and_always_are_explicit_and_do_not_change_risk_policy():
    assert not assess_review_risk("投资", mode="off").should_review
    assert assess_review_risk("你好", mode="always").should_review
    result = assess_review_risk("10月21日的投资建议〔c1〕", decision_card=True)
    assert set(result.reasons) == {
        "concrete_date",
        "health_legal_investment",
        "chart_or_evidence",
        "decision_card",
    }


@pytest.mark.parametrize(
    "changes", [{"mode": "unknown"}, {"decision_card": 1}, {"memory_reference": "true"}]
)
def test_invalid_modes_and_context_are_not_silently_coerced(changes):
    with pytest.raises(ValueError):
        assess_review_risk("合成回答", **changes)

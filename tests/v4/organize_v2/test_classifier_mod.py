"""Synthetic contract/development tests; never import, enumerate, or score blind B."""

from dataclasses import replace

import pytest

from mingjing_core.organize.v2.classifier import LocalClassifier, classify, classify_batch
from mingjing_core.organize.v2.contracts import ClassificationContext, ClassifierSettings
from mingjing_core.organize.v2.ngrams import char_ngrams

CASES = (
    ("daily", "周末想逛博物馆，再找家咖啡馆坐坐。"),
    ("daily", "番茄和鸡蛋怎么炒好吃，想找一个菜谱。"),
    ("daily", "这部电影里的角色和小说有什么区别？"),
    ("daily", "出游的酒店订好了，接下来看看附近的景点。"),
    ("career", "面试还有三天，我想把简历里的项目讲清楚。"),
    ("career", "准备研究生入学考试，想安排复习和刷题。"),
    ("career", "客户又改需求了，项目交付和验收要怎么协调？"),
    ("career", "新岗位是否值得跳槽，要问清试用期考核。"),
    ("relationships", "男朋友几天没有回消息，我们正在冷战。"),
    ("relationships", "朋友聚会让我有些被排斥，想谈谈人际边界。"),
    ("relationships", "和室友吵架后，怎么道歉又不放弃自己的边界？"),
    ("relationships", "分手后还是想念前任，复合这件事该怎么谈？"),
    ("family", "爸妈来住一阵，我们想讨论家务分工。"),
    ("family", "孩子到了上幼儿园的年纪，接送要怎么安排？"),
    ("family", "母亲手术后需要陪护，家人想轮流照顾。"),
    ("family", "过年要去看爷爷奶奶，全家商量探亲计划。"),
    ("wellbeing", "凌晨又醒了，想把睡眠和作息调回来。"),
    ("wellbeing", "膝盖跑步后疼，想找医生看看。"),
    ("wellbeing", "最近焦虑到心慌，想了解心理咨询。"),
    ("wellbeing", "体检报告出来了，想准备复诊要问医生的问题。"),
    ("finance", "每月支出超预算，想先整理账单。"),
    ("finance", "首付不够，想计算房贷月供能否负担。"),
    ("finance", "这笔贷款的利率和还款方式要比较一下。"),
    ("finance", "基金回撤后想调整仓位，先评估风险承受能力。"),
    ("metaphysics", "八字里面正印和偏印有什么区别？"),
    ("metaphysics", "想学习紫微斗数里的四化和三方四正。"),
    ("metaphysics", "占星里太阳星座和上升星座的含义分别是什么？"),
    ("metaphysics", "塔罗牌义里的正位和逆位该怎样解释？"),
)


@pytest.mark.parametrize("expected,text", CASES)
def test_explicit_area_semantics(expected, text):
    result = classify(text)
    assert result.area_id == expected
    assert not result.waiting and 0 <= result.confidence <= 1
    assert set(result.scores) == {item[0] for item in CASES}


@pytest.mark.parametrize(
    "text", ["", "嗯", "我还没想好说什么", "先不聊前面的事了", "abcdefgh 789", "今天只是路过，先问一声好"]
)
def test_no_evidence_abstains_instead_of_defaulting_daily(text):
    result = classify(text)
    assert result.area_id is None and result.waiting


def test_equal_competing_domains_are_waiting():
    result = classify("面试和体检这两件事我都想聊")
    assert result.waiting and result.reason == "ambiguous_areas"


def test_same_topic_ten_turns_are_stable_without_true_label_context():
    texts = ["这次面试准备讲简历里的项目成果。"] + ["接着刚才这件事，再具体说一下那一步。"] * 10
    results = classify_batch(texts)
    assert {result.area_id for result in results} == {"career"}


def test_clear_topic_change_beats_old_context_and_unclear_switch_resets():
    context = ClassificationContext("career", 0.9, previous_text="我们在准备面试")
    new = classify("换个话题，我想学习紫微斗数的四化。", context)
    assert new.area_id == "metaphysics"
    assert classify("换个话题，但我还没想好内容。", context).waiting


def test_explicit_focus_uses_the_current_question_not_earlier_cause():
    result = classify("因为妈妈住院，工作选择也受影响；这次重点是面试岗位和试用期考核。")
    assert result.area_id == "career"


def test_no_ambient_context_survives_between_calls_or_batches():
    classifier = LocalClassifier()
    assert classifier.classify("面试要准备简历").area_id == "career"
    assert classifier.classify("好的").waiting
    assert classify_batch(["面试要准备简历", "刚才这件事继续聊"])[-1].area_id == "career"
    assert classify_batch(["刚才这件事继续聊"])[-1].waiting


def test_inactive_context_does_not_carry_a_topic():
    context = ClassificationContext("finance", 0.9, topic_active=False)
    assert classify("刚才那件事继续", context).waiting


def test_prediction_and_context_are_immutable_copies():
    texts = ["合成上下文"]
    context = ClassificationContext("career", recent_texts=texts)
    texts.clear()
    assert context.recent_texts == ("合成上下文",)
    result = classify("要准备面试和简历")
    with pytest.raises(TypeError):
        result.scores["career"] = 0


def test_configuration_limits_and_ngram_normalization():
    with pytest.raises(ValueError):
        ClassifierSettings(minimum_confidence=float("nan"))
    with pytest.raises(ValueError):
        ClassifierSettings(context_weight=True)
    assert char_ngrams("ＯＦＦＥＲ") == char_ngrams("offer")
    stricter = LocalClassifier(replace(ClassifierSettings(), minimum_evidence=10))
    assert stricter.classify("面试").waiting


@pytest.mark.parametrize("value", [None, {}, [], 3, True])
def test_private_body_type_boundary(value):
    with pytest.raises(ValueError):
        classify(value)


def test_batch_never_accepts_rows_with_evaluation_labels_as_features():
    with pytest.raises(ValueError):
        classify_batch([{"content": "合成正文", "expected_space": "career"}])

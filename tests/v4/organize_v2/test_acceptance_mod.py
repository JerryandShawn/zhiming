"""Independent behavior examples; no sealed B text, labels, scores or tuning feedback enter here."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from mingjing_core.organize.contracts import Message
from mingjing_core.organize.v2.classifier import LocalClassifier
from mingjing_core.organize.v2.contracts import ClassificationContext
from mingjing_core.organize.v2.onnx_port import OnnxConfig, OnnxEncoderPort
from mingjing_core.organize.v2.scoped import (
    OrganizeScope,
    ScopedContext,
    classify_message,
)

TRUTH = json.loads((Path(__file__).parent / "fixtures/semantic_expected_mod.json").read_bytes())


@pytest.mark.parametrize("case", TRUTH["clear"], ids=lambda item: item["area"])
def test_explicit_area_semantics_use_all_seven_documented_areas(case):
    result = LocalClassifier().classify(case["text"])
    assert result.area_id == case["area"]
    assert not result.waiting and 0 <= result.confidence <= 1


@pytest.mark.parametrize("text", TRUTH["uncertain"])
def test_empty_uninformative_and_equal_cross_area_messages_remain_unorganized(text):
    result = LocalClassifier().classify(text)
    assert result.area_id is None and result.waiting


def test_ten_turns_of_same_topic_do_not_jump_away_and_explicit_new_topic_wins():
    classifier = LocalClassifier()
    first = "明天参加产品经理岗位面试，继续准备自我介绍和项目经历。"
    initial = classifier.classify(first)
    assert initial.area_id == "career"
    context = ClassificationContext("career", initial.confidence, (first,), first, True, "synthetic-topic")
    for text in TRUTH["continuations"]:
        result = classifier.classify(text, context=context)
        assert result.area_id == "career", text
        context = replace(
            context,
            previous_area_id=result.area_id,
            previous_confidence=result.confidence,
            recent_texts=(*context.recent_texts, text)[-3:],
            previous_text=text,
        )
    changed = classifier.classify(TRUTH["hard_change"], context=context)
    assert changed.area_id == "finance"


def test_inactive_topic_context_cannot_classify_a_new_ambiguous_message():
    context = ClassificationContext("career", 0.99, ("上一个人的面试安排",), "面试安排", False)
    assert LocalClassifier().classify("这个呢？", context=context).waiting


def test_instances_and_calls_have_no_ambient_previous_owner_context():
    classifier = LocalClassifier()
    first = classifier.classify("我想学习八字十神和紫微斗数四化。")
    assert first.area_id == "metaphysics"
    assert classifier.classify("这个呢？").waiting
    assert LocalClassifier().classify("这个呢？").waiting
    explicit = ClassificationContext("career", 0.95, ("准备面试",), "准备面试")
    assert classifier.classify("继续刚才这个话题", context=explicit).area_id == "career"
    assert classifier.classify("继续刚才这个话题").waiting


def test_empty_message_does_not_turn_into_assigned_content_even_with_context():
    context = ClassificationContext("career", 0.95, ("面试",), "面试")
    assert LocalClassifier().classify(" ", context=context).waiting


def test_prediction_scores_are_immutable_copies():
    prediction = LocalClassifier().classify("我想比较基金手续费和定期存款利率。")
    with pytest.raises(TypeError):
        prediction.scores["daily"] = 100


def test_onnx_default_and_blank_path_never_call_a_loader_or_download_a_model():
    calls = []

    def forbidden_loader(*args):
        calls.append(args)
        raise AssertionError("No loader is authorized in this test")

    for config in (None, OnnxConfig(model_path=""), OnnxConfig(model_path="   ")):
        port = OnnxEncoderPort(config)
        assert not port.enabled
        assert port.activate(forbidden_loader) is False
        assert port.encode(("合成文本",)) is None
    assert not calls


def test_configured_onnx_path_still_requires_an_explicit_host_activation():
    port = OnnxEncoderPort(OnnxConfig(model_path="synthetic-local-model.onnx"))
    assert not port.enabled and port.encode(("合成文本",)) is None


def scoped_message(**changes):
    item = Message("synthetic", "user", "继续刚才这个话题", 0, "owner", "self", thread_id="thread")
    return replace(item, **changes)


@pytest.mark.parametrize(
    "field,value",
    [("owner_id", "other"), ("subject_id", "other"), ("thread_id", "other")],
)
def test_scope_entry_rejects_foreign_message_and_context_before_semantic_routing(field, value):
    scope = OrganizeScope("owner", "self", "thread")
    context = ClassificationContext("career", 0.95, ("准备面试",), "准备面试")
    with pytest.raises(ValueError):
        classify_message(scoped_message(**{field: value}), scope=scope)
    foreign = replace(scope, **{field: value})
    with pytest.raises(ValueError):
        classify_message(scoped_message(), scope=scope, context=ScopedContext(foreign, context))


@pytest.mark.parametrize(
    "change",
    [
        {"status": "deleted"},
        {"incognito": True},
        {"retention_scope": "ephemeral"},
        {"role": "assistant"},
    ],
)
def test_persistent_routing_rejects_retracted_private_and_assistant_messages(change):
    with pytest.raises(ValueError):
        classify_message(scoped_message(**change), scope=OrganizeScope("owner", "self", "thread"))


def test_valid_scoped_context_routes_without_retaining_a_previous_call():
    scope = OrganizeScope("owner", "self", "thread")
    context = ScopedContext(scope, ClassificationContext("career", 0.95, ("准备面试",), "准备面试"))
    assert classify_message(scoped_message(), scope=scope, context=context).area_id == "career"
    assert classify_message(scoped_message(), scope=scope).waiting

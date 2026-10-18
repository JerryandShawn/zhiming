"""Offline behavioral contracts for segmentation and sticky scoped routing."""

from dataclasses import replace

import pytest

from mingjing_core.organize.contracts import Message, Topic, TopicCatalog
from mingjing_core.organize.router import Router
from mingjing_core.organize.segmenter import Segmenter
from mingjing_core.organize.space_classifier import SpaceClassifier

OWNER = "synthetic-owner"
SUBJECT = "synthetic-subject"
HOUR_MS = 3_600_000


def message(text: str, *, ident: str = "m0", at: int = 0, role: str = "user") -> Message:
    return Message(ident, role, text, at, OWNER, SUBJECT)


def topic(ident: str, space: str, text: str) -> Topic:
    return Topic(ident, space, text, (), (), 0, 0, (), text)


def catalog(*topics: Topic) -> TopicCatalog:
    return TopicCatalog(OWNER, SUBJECT, topics)


@pytest.mark.parametrize("gap_ms,expected", [(6 * HOUR_MS, 1), (6 * HOUR_MS + 1, 2)])
def test_time_gap_requires_strictly_more_than_six_hours(gap_ms: int, expected: int) -> None:
    messages = [message("准备面试和简历"), message("准备面试和简历", ident="m1", at=gap_ms)]
    segments = Segmenter().segment(messages)
    assert len(segments) == expected
    assert tuple(ident for part in segments for ident in part.message_ids) == ("m0", "m1")


def test_topic_shift_occurs_at_user_turn_and_preserves_assistant_response() -> None:
    messages = [
        message("跳槽面试的简历怎样准备"),
        message("我们可以先整理家庭住院照护的注意事项", ident="m1", at=1, role="assistant"),
        message("对了，我妈最近住院了，需要家人照顾", ident="m2", at=2),
        message("先和家人确认陪诊安排", ident="m3", at=3, role="assistant"),
    ]
    segments = Segmenter().segment(messages)
    assert tuple(part.message_ids for part in segments) == (("m0", "m1"), ("m2", "m3"))
    assert "住院照护" not in segments[0].user_text
    assert "住院照护" in segments[0].text


@pytest.mark.parametrize(
    "messages",
    [
        [message("工作", at=2), message("工作", ident="m1", at=1)],
        [message("工作"), message("面试", at=1)],
        [message("工作"), replace(message("工作", ident="m1", at=1), owner_id="different-owner")],
        [message("工作"), replace(message("工作", ident="m1", at=1), subject_id="different-subject")],
    ],
)
def test_segmentation_rejects_disordered_duplicate_and_cross_scope_inputs(messages: list[Message]) -> None:
    with pytest.raises(ValueError):
        Segmenter().segment(messages)


def test_empty_history_has_no_synthetic_segment() -> None:
    assert Segmenter().segment([]) == ()


@pytest.mark.parametrize("text", ["嗯", "这件事情还没有更多信息", "", "暂时不知道说什么"])
def test_low_confidence_is_daily_and_requires_review(text: str) -> None:
    decision = SpaceClassifier().classify(text)
    assert decision.space_id == "daily"
    assert decision.needs_review
    assert 0 <= decision.confidence <= 1


def test_relative_hospitalisation_is_primarily_family() -> None:
    decision = SpaceClassifier().classify("对了，我妈最近住院了")
    assert decision.space_id == "family"
    assert not decision.needs_review


def test_same_career_topic_remains_sticky_for_ten_user_turns() -> None:
    active = topic("career-interview", "career", "跳槽面试简历招聘求职")
    other = topic("career-exam", "career", "考研备考复习考试上岸")
    directory = catalog(active, other)
    router = Router()
    turns = (
        "跳槽前想准备面试",
        "求职的简历已经写完",
        "招聘面试要怎样练习",
        "简历要再修改一下",
        "面试可能下周开始",
        "这次求职机会怎样比较",
        "关于跳槽面试还有个问题",
        "招聘方让我发简历",
        "面试之后等录用消息",
        "求职拿到offer了",
    )
    for index, text in enumerate(turns):
        result = router.route(message(text, ident=f"turn-{index}", at=index), directory, active.id)
        assert result.space_id == "career", (index, result)
        assert result.topic_id == active.id, (index, result)


def test_clear_switch_to_family_overrides_current_career_topic() -> None:
    active = topic("career-interview", "career", "跳槽面试简历招聘求职")
    result = Router().route(message("对了，我妈最近住院了"), catalog(active), active.id)
    assert result.space_id == "family"
    assert result.topic_id is None


def test_matches_another_topic_in_the_same_space_before_creating_one() -> None:
    interview = topic("career-interview", "career", "跳槽面试简历招聘求职")
    exam = topic("career-exam", "career", "考研备考复习考试上岸")
    result = Router().route(message("考研复习考试应该怎样备考"), catalog(interview, exam), interview.id)
    assert result.space_id == "career"
    assert result.topic_id == exam.id


@pytest.mark.parametrize(
    "text,expected_space",
    [("这个放到家庭里", "family"), ("这个放到感情里", "relationships"), ("切到感情", "relationships")],
)
def test_explicit_user_routing_beats_inferred_current_topic(text: str, expected_space: str) -> None:
    active = topic("career-interview", "career", "跳槽面试简历招聘求职")
    result = Router().route(message(text), catalog(active), active.id)
    assert result.space_id == expected_space
    assert result.source == "user"
    assert result.topic_id is None


def test_explicit_new_topic_does_not_reuse_semantically_matching_existing_topic() -> None:
    house = topic("finance-house", "finance", "买房首付房贷预算")
    result = Router().route(message("开个新话题聊买房"), catalog(house), house.id)
    assert result.space_id == "finance"
    assert result.topic_id is None
    assert result.source == "user"


@pytest.mark.parametrize("field", ["owner_id", "subject_id"])
def test_route_rejects_catalog_scope_mismatch(field: str) -> None:
    inbound = replace(message("准备跳槽面试"), **{field: "unauthorized-scope"})
    with pytest.raises(ValueError):
        Router().route(inbound, catalog())


def test_unknown_current_topic_is_rejected_instead_of_silently_guessing_scope() -> None:
    with pytest.raises(ValueError):
        Router().route(message("准备面试简历"), catalog(), "unknown-topic")


def test_empty_catalog_creates_a_topic_without_fabricating_a_persisted_id() -> None:
    decision = Router().route(message("准备跳槽面试和简历"), catalog())
    assert decision.space_id == "career"
    assert decision.topic_id is None
    assert not decision.needs_review

"""Topic candidates are separated by meaning, source scope and explicit waiting status."""

from dataclasses import replace

import pytest

from mingjing_core.organize.contracts import Message
from mingjing_core.organize.v2.contracts import Prediction
from mingjing_core.organize.v2.scoped import OrganizeScope
from mingjing_core.organize.v2.topics import cluster_messages

SCOPE = OrganizeScope("owner", "self", "thread1")


def message(ident, text, at):
    return Message(ident, "user", text, at, "owner", "self", thread_id="thread1")


def prediction(area="career"):
    return Prediction(area, 0.9, {"career": 3}, "synthetic_test_projection")


def test_repeated_interview_and_unrelated_exam_are_distinct_topics():
    messages = [
        message("a", "面试简历项目经历复盘", 1),
        message("b", "面试简历项目经历继续复盘", 2),
        message("c", "考研数学英语刷题背单词", 3),
    ]
    topics = cluster_messages(messages, {item.id: prediction() for item in messages}, scope=SCOPE)
    groups = {frozenset(topic.message_ids) for topic in topics}
    assert groups == {frozenset({"a", "b"}), frozenset({"c"})}


def test_waiting_messages_do_not_become_a_certain_life_topic():
    messages = [message("a", "这件事说不上", 1)]
    topic = cluster_messages(messages, {"a": prediction(None)}, scope=SCOPE)[0]
    assert topic.space_id == "__unorganized__" and topic.title == "待确认"


def test_topic_ids_include_scope_and_cross_scope_messages_are_rejected():
    item = message("a", "面试项目复盘", 1)
    first = cluster_messages([item], {"a": prediction()}, scope=SCOPE)[0]
    other = OrganizeScope("other", "self", "thread1")
    with pytest.raises(ValueError):
        cluster_messages([item], {"a": prediction()}, scope=other)
    second = cluster_messages([replace(item, owner_id="other")], {"a": prediction()}, scope=other)[0]
    assert first.id != second.id


def test_revoked_sources_and_missing_predictions_are_not_clustered():
    item = message("a", "面试项目复盘", 1)
    with pytest.raises(ValueError):
        cluster_messages([replace(item, status="deleted")], {"a": prediction()}, scope=SCOPE)
    with pytest.raises(ValueError):
        cluster_messages([item], {}, scope=SCOPE)


@pytest.mark.parametrize("threshold", [True, False, None, "0.4", -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_topic_threshold_is_rejected_even_without_messages(threshold):
    with pytest.raises(ValueError, match="阈值"):
        cluster_messages([], {}, scope=SCOPE, similarity_threshold=threshold)

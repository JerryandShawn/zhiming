"""Scoped topic candidate adapter reuses the old clusterer with local character vectors."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from math import isfinite

from mingjing_core.organize.contracts import (
    Message,
    Segment,
    SpaceDecision,
    Topic,
    stable_id,
)
from mingjing_core.organize.topic_clusterer import TopicClusterer

from .contracts import Prediction
from .ngrams import char_ngrams
from .scoped import OrganizeScope, require_message


class CharacterVectorizer:
    def encode(self, text: str) -> dict[str, float]:
        return char_ngrams(text)


def _segment(message: Message) -> Segment:
    vector = char_ngrams(message.content)
    keywords = tuple(sorted(vector, key=lambda word: (-vector[word], word))[:8])
    return Segment(
        message.id,
        (message.id,),
        message.at_ms,
        message.at_ms,
        keywords,
        message.content,
        message.content,
    )


def cluster_messages(
    messages: Sequence[Message],
    predictions: Mapping[str, Prediction],
    *,
    scope: OrganizeScope,
    similarity_threshold: float = 0.4,
) -> tuple[Topic, ...]:
    """One user message per segment; ground truth and context-group labels are never inputs."""
    if (
        isinstance(similarity_threshold, bool)
        or not isinstance(similarity_threshold, (int, float))
        or not isfinite(similarity_threshold)
        or not 0 <= similarity_threshold <= 1
    ):
        raise ValueError("话题聚类阈值无效")
    for message in messages:
        require_message(message, scope)
    ids = [message.id for message in messages]
    if len(set(ids)) != len(ids) or set(predictions) != set(ids):
        raise ValueError("话题归区结果与消息不一致")
    if any(not isinstance(prediction, Prediction) for prediction in predictions.values()):
        raise ValueError("话题需要分类器实际预测")
    ordered = sorted(messages, key=lambda message: (message.at_ms, message.id))
    decisions = {
        ident: SpaceDecision(value.area_id or "__unorganized__", value.confidence, value.waiting)
        for ident, value in predictions.items()
    }
    topics = TopicClusterer(CharacterVectorizer(), similarity_threshold).cluster(
        tuple(_segment(message) for message in ordered), decisions
    )
    return tuple(
        replace(
            topic,
            id=stable_id(
                "topic_v2_",
                (scope.owner_id, scope.subject_id, scope.thread_id, topic.id),
            ),
        )
        for topic in topics
    )

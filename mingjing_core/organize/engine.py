"""The public offline pipeline: messages -> segments -> labels -> editable proposal."""

from collections.abc import Sequence

from .contracts import Message, MessageLabel, SpaceDecision
from .local_vectors import Vectorizer
from .onnx_vectors import configured_vectorizer
from .proposal import Proposal
from .segmenter import Segmenter, validate_messages
from .space_classifier import SpaceClassifier
from .topic_clusterer import TopicClusterer


class OrganizeEngine:
    def __init__(self, vectorizer: Vectorizer | None = None) -> None:
        self.vectorizer = vectorizer or configured_vectorizer()
        self.segmenter = Segmenter(self.vectorizer)
        self.classifier = SpaceClassifier(self.vectorizer)
        self.clusterer = TopicClusterer(self.vectorizer)

    def organize(self, messages: Sequence[Message]) -> Proposal:
        validate_messages(messages)
        if not messages:
            raise ValueError("请提供至少一条有效消息")
        segments = self.segmenter.segment(messages)
        decisions = {
            segment.id: self.classifier.classify(segment.user_text)
            if segment.user_text
            else SpaceDecision("daily", 0.0, True)
            for segment in segments
        }
        topics = self.clusterer.cluster(segments, decisions)
        review_ids = tuple(
            message_id
            for segment in segments
            if decisions[segment.id].needs_review
            for message_id in segment.message_ids
        )
        labels = tuple(
            MessageLabel(
                message_id,
                decisions[segment.id].space_id,
                decisions[segment.id].secondary,
                decisions[segment.id].confidence,
                decisions[segment.id].needs_review,
            )
            for segment in segments
            for message_id in segment.message_ids
        )
        return Proposal(
            messages[0].owner_id,
            messages[0].subject_id,
            topics,
            review_ids,
            self.vectorizer.mode,
            self.vectorizer.degradation,
            tuple(messages),
            labels,
        )

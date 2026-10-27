"""A local pre-router only; decisions never mutate messages or model state."""

import re

from .contracts import Message, RouteDecision, TopicCatalog
from .local_vectors import KeywordVectorizer, Vectorizer, cosine
from .space_classifier import SpaceClassifier
from .spaces import DEFAULT_SPACES


class Router:
    def __init__(
        self, vectorizer: Vectorizer | None = None, sticky_threshold: float = 0.35
    ) -> None:
        if not 0 <= sticky_threshold <= 1:
            raise ValueError("路由参数无效")
        self.vectorizer = vectorizer or KeywordVectorizer()
        self.classifier = SpaceClassifier(self.vectorizer)
        self.sticky_threshold = sticky_threshold

    def route(
        self,
        message: Message,
        catalog: TopicCatalog,
        current_topic_id: str | None = None,
    ) -> RouteDecision:
        if message.role != "user" or (message.owner_id, message.subject_id) != (
            catalog.owner_id,
            catalog.subject_id,
        ):
            raise ValueError("消息与话题目录归属不一致")
        current = next(
            (topic for topic in catalog.topics if topic.id == current_topic_id), None
        )
        if current_topic_id is not None and current is None:
            raise ValueError("当前话题不在有效目录")
        explicit = self._explicit_space(message.content)
        decision = self.classifier.classify(message.content)
        space_id = explicit or decision.space_id
        if re.search(r"(?:开|建|新建)(?:个|一个)?新话题", message.content):
            return RouteDecision(
                space_id, None, 1.0, "user", decision.needs_review and explicit is None
            )
        vector = self.vectorizer.encode(message.content)
        if current is not None and explicit in {None, current.space_id}:
            similarity = cosine(
                vector, self.vectorizer.encode(current.title + " " + current.summary)
            )
            if decision.needs_review or (
                space_id == current.space_id and similarity >= self.sticky_threshold
            ):
                return RouteDecision(
                    current.space_id,
                    current.id,
                    max(decision.confidence, similarity),
                    "sticky",
                )
        candidates = []
        for topic in catalog.topics:
            if topic.space_id == space_id:
                similarity = cosine(
                    vector, self.vectorizer.encode(topic.title + " " + topic.summary)
                )
                candidates.append((similarity, topic.id))
        score, topic_id = max(
            candidates, default=(0.0, None), key=lambda item: (item[0], item[1] or "")
        )
        return RouteDecision(
            space_id,
            topic_id if score >= self.sticky_threshold else None,
            1.0 if explicit else decision.confidence,
            "user" if explicit else decision.source,
            decision.needs_review and explicit is None,
        )

    @staticmethod
    def _explicit_space(text: str) -> str | None:
        match = re.search(
            r"(?:这个放到|放到|切到|归入|移到|转到)\s*([^，。！？\n]{1,12})", text
        )
        if match is None:
            return None
        candidate = match.group(1)
        for space in DEFAULT_SPACES:
            aliases = (
                space.name,
                space.id,
                "事业" if space.id == "career" else space.name,
                "感情" if space.id == "relationships" else space.name,
            )
            if any(candidate.startswith(alias) for alias in aliases):
                return space.id
        return None

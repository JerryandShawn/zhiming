"""Deterministic incremental clustering within a space, with a small recency prior."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .contracts import Segment, SpaceDecision, Topic, stable_id
from .local_vectors import KeywordVectorizer, Vectorizer, cosine


@dataclass
class _Bucket:
    space_id: str
    needs_review: bool = False
    segments: list[Segment] = field(default_factory=list)
    vector: Counter[str] = field(default_factory=Counter)

    def add(self, segment: Segment, vector: Mapping[str, float]) -> None:
        self.segments.append(segment)
        self.vector.update(vector)

    def topic(self) -> Topic:
        ids = tuple(item.id for item in self.segments)
        word_counts = Counter(word for item in self.segments for word in item.keywords)
        words = tuple(sorted(word_counts, key=lambda word: (-word_counts[word], -len(word), word))[:8])
        title = "待确认" if self.needs_review else "·".join(words[:2]) or "最近近况"
        return Topic(
            stable_id("topic_", (self.space_id, ids[0])),
            self.space_id,
            title,
            ids,
            tuple(message_id for item in self.segments for message_id in item.message_ids),
            self.segments[0].start,
            self.segments[-1].end,
            words,
            self.segments[0].user_text[:80] or self.segments[0].text[:80],
        )


class TopicClusterer:
    def __init__(self, vectorizer: Vectorizer | None = None, similarity_threshold: float = 0.4) -> None:
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("聚类参数无效")
        self.vectorizer = vectorizer or KeywordVectorizer()
        self.threshold = similarity_threshold

    def cluster(self, segments: Sequence[Segment], decisions: Mapping[str, SpaceDecision]) -> tuple[Topic, ...]:
        if len({item.id for item in segments}) != len(segments) or set(decisions) != {item.id for item in segments}:
            raise ValueError("片段与归区不一致")
        if any(left.start > right.start for left, right in zip(segments, segments[1:], strict=False)):
            raise ValueError("片段需要按时间排序")
        buckets: list[_Bucket] = []
        for segment in segments:
            space_id = decisions[segment.id].space_id
            needs_review = decisions[segment.id].needs_review
            vector = self.vectorizer.encode(segment.user_text or segment.text)
            candidates = [
                (self._score(bucket, segment, vector), index)
                for index, bucket in enumerate(buckets)
                if bucket.space_id == space_id and bucket.needs_review == needs_review
            ]
            # Uncertain fragments form an explicit review tray, not an asserted shared life topic.
            if needs_review:
                candidates = [
                    (1.0, index)
                    for index, bucket in enumerate(buckets)
                    if bucket.space_id == space_id and bucket.needs_review
                ]
            score, index = max(candidates, default=(0.0, -1), key=lambda item: (item[0], -item[1]))
            if score < self.threshold or index < 0:
                buckets.append(_Bucket(space_id, needs_review))
                index = len(buckets) - 1
            buckets[index].add(segment, vector)
        return tuple(bucket.topic() for bucket in buckets)

    @staticmethod
    def _score(bucket: _Bucket, segment: Segment, vector: Mapping[str, float]) -> float:
        similarity = cosine(vector, bucket.vector)
        # Recency cannot merge unrelated topics merely because they happened together.
        days = max(0, segment.start - bucket.segments[-1].end) / 86_400_000
        return similarity + (0.04 / (1 + days) if similarity >= 0.25 else 0.0)

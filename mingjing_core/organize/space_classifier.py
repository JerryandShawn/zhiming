"""Fusion of editable keyword rules and local description similarity."""

import re
from collections.abc import Sequence

from .contracts import SpaceDecision
from .local_vectors import KeywordVectorizer, Vector, Vectorizer, cosine
from .spaces import DEFAULT_SPACES, Space


class SpaceClassifier:
    def __init__(
        self,
        vectorizer: Vectorizer | None = None,
        spaces: Sequence[Space] = DEFAULT_SPACES,
        confidence_threshold: float = 0.4,
    ) -> None:
        if not 0 <= confidence_threshold <= 1 or len(
            {space.id for space in spaces}
        ) != len(spaces):
            raise ValueError("归区参数无效")
        if "daily" not in {space.id for space in spaces}:
            raise ValueError("必须提供默认日常区")
        self.vectorizer = vectorizer or KeywordVectorizer()
        self.spaces = tuple(spaces)
        self.threshold = confidence_threshold
        self._descriptions = {
            space.id: self.vectorizer.encode(
                space.description + "、".join(space.keywords)
            )
            for space in spaces
        }

    def classify(self, text: str) -> SpaceDecision:
        folded = text.casefold()
        vector = self.vectorizer.encode(text)
        scores = self._scores(folded, vector)
        focus = re.split(r"这里先|这次重点是|当前主要|重点是|先比较|先聊", folded)[-1]
        if focus != folded:
            focused = self._scores(focus, self.vectorizer.encode(focus))
            scores = {
                key: value * 0.4 + focused[key] * 2 for key, value in scores.items()
            }
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        first, second = ranked[0], ranked[1] if len(ranked) > 1 else ("daily", 0.0)
        confidence = first[1] / (first[1] + second[1] + 0.7) if first[1] else 0.0
        low = confidence < self.threshold
        secondary = (
            second[0] if second[1] >= 1.2 and second[1] >= first[1] * 0.2 else None
        )
        return SpaceDecision(
            "daily" if low else first[0],
            confidence,
            low,
            secondary if not low else None,
            "embedding" if self.vectorizer.mode == "onnx" else "rule",
        )

    def _scores(self, text: str, vector: Vector) -> dict[str, float]:
        scores = {}
        for space in self.spaces:
            rule = sum(
                1.0 + min(len(word), 4) * 0.1 for word in space.keywords if word in text
            )
            similarity = max(0.0, cosine(vector, self._descriptions[space.id]))
            scores[space.id] = rule + similarity * 1.5
        # A relative's treatment is primarily a family-care topic, not the speaker's medical history.
        if scores.get("family", 0) >= 1.2 and any(
            word in text for word in ("住院", "复诊", "照顾", "照护", "陪诊")
        ):
            scores["family"] += 1.5
        return scores

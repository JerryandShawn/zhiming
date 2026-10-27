"""CPU-only sparse fallback; an injected local encoder may replace it."""

import math
import re
from collections import Counter
from collections.abc import Mapping
from typing import Protocol

from .spaces import DEFAULT_SPACES
from .synonyms import SYNONYMS

Vector = Mapping[str, float]
_GRAM_STOP = frozenset(
    (
        "我想",
        "准备",
        "一个",
        "这次",
        "因为",
        "这里",
        "最近",
        "先聊",
        "这周",
        "怎么",
        "可以",
        "我们",
        "希望",
        "这样",
        "应该",
        "今天",
        "还有",
        "自己",
        "一下",
        "觉得",
        "事情",
        "这件",
    )
)


class Vectorizer(Protocol):
    mode: str
    degradation: str | None

    def encode(self, text: str) -> Vector: ...


def cosine(left: Vector, right: Vector) -> float:
    dot = sum(value * right.get(key, 0.0) for key, value in left.items())
    norm = math.sqrt(
        sum(value * value for value in left.values())
        * sum(value * value for value in right.values())
    )
    return max(-1.0, min(1.0, dot / norm)) if norm else 0.0


class KeywordVectorizer:
    mode = "keyword"

    def __init__(self, degradation: str = "local_model_not_configured") -> None:
        self.degradation = degradation

    def encode(self, text: str) -> Vector:
        folded = text.casefold()
        values: Counter[str] = Counter()
        for group in SYNONYMS:
            if any(word in folded for word in group):
                values["syn:" + group[0]] += 3.0
        for space in DEFAULT_SPACES:
            for word in space.keywords:
                if word in folded:
                    values["word:" + word] += 1.5
        for token in re.findall(r"[a-z0-9]{2,}|[\u3400-\u9fff]+", folded):
            if token.isascii():
                values["text:" + token] += 0.3
            else:
                for index in range(len(token) - 1):
                    gram = token[index : index + 2]
                    if gram not in _GRAM_STOP:
                        values["gram:" + gram] += 0.15
        return values


def keywords(text: str, limit: int = 8) -> tuple[str, ...]:
    folded = text.casefold()
    words = {
        word for space in DEFAULT_SPACES for word in space.keywords if word in folded
    }
    return tuple(
        sorted(words, key=lambda word: (-folded.count(word), -len(word), word))[:limit]
    )

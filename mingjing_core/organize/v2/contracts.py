"""Offline routing projections; confidence is a rule score, not a calibrated probability."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from mingjing_core.organize.spaces import DEFAULT_SPACES

AREA_IDS = frozenset(space.id for space in DEFAULT_SPACES)


def _number(value: object, minimum: float = 0, maximum: float = 1) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError("整理分类数值无效")


@dataclass(frozen=True)
class ClassifierSettings:
    minimum_evidence: float = 1.65
    minimum_confidence: float = 0.60
    minimum_margin: float = 0.48
    ngram_weight: float = 0.50
    context_weight: float = 0.85

    def __post_init__(self) -> None:
        for name in (
            "minimum_evidence",
            "minimum_margin",
            "ngram_weight",
            "context_weight",
        ):
            _number(getattr(self, name), maximum=10)
        _number(self.minimum_confidence)


@dataclass(frozen=True)
class ClassificationContext:
    previous_area_id: str | None = None
    previous_confidence: float = 0.8
    recent_texts: tuple[str, ...] = field(default=(), repr=False)
    previous_text: str | None = field(default=None, repr=False)
    topic_active: bool = True
    topic_id: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.previous_area_id is not None and (
            type(self.previous_area_id) is not str or self.previous_area_id not in AREA_IDS
        ):
            raise ValueError("整理上下文功能区无效")
        _number(self.previous_confidence)
        if type(self.topic_active) is not bool:
            raise ValueError("整理话题开关无效")
        if not isinstance(self.recent_texts, (list, tuple)) or any(type(text) is not str for text in self.recent_texts):
            raise ValueError("整理上下文正文无效")
        if self.previous_text is not None and type(self.previous_text) is not str:
            raise ValueError("整理上下文正文无效")
        object.__setattr__(self, "recent_texts", tuple(self.recent_texts))


@dataclass(frozen=True)
class Prediction:
    area_id: str | None
    confidence: float
    scores: Mapping[str, float]
    reason: str
    secondary_id: str | None = None

    def __post_init__(self) -> None:
        if self.area_id is not None and (type(self.area_id) is not str or self.area_id not in AREA_IDS):
            raise ValueError("整理预测功能区无效")
        if self.secondary_id is not None and (
            type(self.secondary_id) is not str or self.secondary_id not in AREA_IDS or self.secondary_id == self.area_id
        ):
            raise ValueError("整理预测副区无效")
        _number(self.confidence)
        if not isinstance(self.scores, Mapping):
            raise ValueError("整理预测评分无效")
        for key, score in self.scores.items():
            if key not in AREA_IDS:
                raise ValueError("整理评分功能区无效")
            _number(score, maximum=float("inf"))
        object.__setattr__(self, "scores", MappingProxyType(dict(self.scores)))

    @property
    def waiting(self) -> bool:
        return self.area_id is None

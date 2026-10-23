"""Scoped read projections for P5b B; these never register tools or authorize persistence."""

from dataclasses import dataclass, field
from math import isfinite
from typing import Literal

from mingjing_core.memory.retrieval_types import SearchUnit, SourceRef

Layer = Literal["profile", "open_topic", "round", "summary", "retrieval"]


def finite_score(value: float) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return value >= 0 and isfinite(value * 1.5)
    except OverflowError:
        return False


def text_identity(*values: str) -> None:
    if any(not isinstance(value, str) or not value.strip() or len(value) > 250 for value in values):
        raise ValueError("partition_identity_invalid")


@dataclass(frozen=True)
class PartitionScope:
    owner_id: str
    subject_id: str
    life_thread_id: str
    space_id: str
    topic_id: str | None = None

    def __post_init__(self) -> None:
        text_identity(self.owner_id, self.subject_id, self.life_thread_id, self.space_id)
        if self.topic_id is not None:
            text_identity(self.topic_id)


@dataclass(frozen=True)
class PartitionRecord:
    unit: SearchUnit = field(repr=False)
    life_thread_id: str
    space_id: str
    layer: Layer
    topic_id: str | None = None
    score: float = 0.0
    title: str = field(default="", repr=False)
    revision: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.unit, SearchUnit):
            raise ValueError("partition_unit_required")
        text_identity(self.life_thread_id, self.space_id)
        if self.topic_id is not None:
            text_identity(self.topic_id)
        if self.layer not in {"profile", "open_topic", "round", "summary", "retrieval"}:
            raise ValueError("partition_layer_invalid")
        if not finite_score(self.score):
            raise ValueError("partition_score_invalid")
        if not isinstance(self.title, str) or type(self.revision) is not int or self.revision < 1:
            raise ValueError("partition_revision_or_title_invalid")
        if self.layer == "round" and (self.unit.kind != "round" or self.topic_id is None):
            raise ValueError("partition_round_requires_topic_and_pair")
        if self.layer == "profile" and (
            self.unit.kind not in {"fact", "event", "fact_event"} or self.unit.origin != "user" or self.unit.inferred
        ):
            raise ValueError("partition_profile_requires_user_fact")
        if self.layer == "open_topic" and not self.title.strip():
            raise ValueError("partition_open_topic_requires_title")
        if self.layer == "summary" and (
            self.unit.kind != "summary" or self.unit.origin != "derived_summary" or not self.unit.inferred
        ):
            raise ValueError("partition_summary_must_be_marked_derived")


@dataclass(frozen=True)
class ContextLine:
    id: str
    revision: int
    space_id: str
    topic_id: str | None
    text: str = field(repr=False)
    source_refs: tuple[SourceRef, ...]
    weighted_score: float
    attribution: str
    abbreviated: bool


@dataclass(frozen=True)
class PartitionedContext:
    scope: PartitionScope
    source_epoch: int
    constraints: tuple[ContextLine, ...] = field(repr=False)
    profile: tuple[ContextLine, ...] = field(repr=False)
    open_topics: tuple[ContextLine, ...] = field(repr=False)
    rounds: tuple[ContextLine, ...] = field(repr=False)
    current_summary: tuple[ContextLine, ...] = field(repr=False)
    recent_elsewhere: tuple[ContextLine, ...] = field(repr=False)
    retrieval: tuple[ContextLine, ...] = field(repr=False)
    omitted_ids: tuple[str, ...]
    projection_key: str


@dataclass(frozen=True)
class SummaryInvalidation:
    id: str
    expected_revision: int
    reason: str


@dataclass(frozen=True)
class SummaryInvalidationPlan:
    scope: PartitionScope
    source_epoch: int
    changes: tuple[SummaryInvalidation, ...]
    operation_id: str

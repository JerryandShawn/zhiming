"""Scoped gap ranking and cooldown projections; never mutate facts or ask a model."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Literal

from mingjing_core.timekit.clock import Clock

from .followups_contracts import FollowupScope, aware


@dataclass(frozen=True)
class GapOption:
    option: str = field(repr=False)
    effect: str = field(repr=False)

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.option, self.effect)
        ):
            raise ValueError("gap option and effect must be explicit")


@dataclass(frozen=True)
class KnowledgeGap:
    id: str
    scope: FollowupScope
    base_priority: int
    decision_impact: tuple[str, ...] = field(default=(), repr=False)
    answer_options: tuple[GapOption, ...] = field(default=(), repr=False)
    related_at: datetime | None = None
    cooldown_until: datetime | None = None
    asked_at: datetime | None = None
    skips: int = 0
    status: Literal["open", "asked", "answered", "dismissed"] = "open"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.scope, FollowupScope)
            or not isinstance(self.id, str)
            or not self.id.strip()
        ):
            raise ValueError("gap requires identity and scope")
        if type(self.base_priority) is not int or not 1 <= self.base_priority <= 5:
            raise ValueError("gap priority must be one to five")
        if (
            type(self.skips) is not int
            or self.skips < 0
            or self.status not in {"open", "asked", "answered", "dismissed"}
        ):
            raise ValueError("invalid gap state")
        if not isinstance(self.decision_impact, tuple) or any(
            not isinstance(value, str) or not value.strip()
            for value in self.decision_impact
        ):
            raise ValueError("gap impacts must be immutable text")
        if not isinstance(self.answer_options, tuple) or (
            self.answer_options and not 2 <= len(self.answer_options) <= 4
        ):
            raise ValueError("gap requires two to four possible answers")
        if any(not isinstance(value, GapOption) for value in self.answer_options):
            raise ValueError("invalid gap option")
        for name in ("related_at", "cooldown_until", "asked_at"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, aware(value))


def gap_priority(gap: KnowledgeGap, *, clock: Clock) -> int:
    now = aware(clock.now())
    recent = gap.related_at is not None and timedelta(
        0
    ) <= now - gap.related_at <= timedelta(days=7)
    cooling = gap.cooldown_until is not None and now < gap.cooldown_until
    score = gap.base_priority + bool(gap.decision_impact) + recent - cooling
    ceiling = 5 if gap.decision_impact and gap.answer_options else 2
    return min(ceiling, max(1, score))


def gaps_for_context(
    gaps: Sequence[KnowledgeGap],
    *,
    scope: FollowupScope,
    clock: Clock,
    paused_until: datetime | None = None,
) -> tuple[KnowledgeGap, ...]:
    now = aware(clock.now())
    if any(gap.scope != scope for gap in gaps) or len({gap.id for gap in gaps}) != len(
        gaps
    ):
        raise ValueError("gap scope or identity conflict")
    if paused_until is not None and now < aware(paused_until):
        return ()
    eligible = [
        gap
        for gap in gaps
        if gap.status in {"open", "asked"}
        and gap.skips < 2
        and (gap.cooldown_until is None or now >= gap.cooldown_until)
    ]
    return tuple(
        sorted(eligible, key=lambda gap: (-gap_priority(gap, clock=clock), gap.id))[:5]
    )


def should_ask_first(gap: KnowledgeGap, *, related_to_current_decision: bool) -> bool:
    if type(related_to_current_decision) is not bool:
        raise ValueError("decision relevance must be explicit")
    return bool(
        related_to_current_decision
        and gap.decision_impact
        and len({option.effect.strip() for option in gap.answer_options}) > 1
    )


def mark_gap_asked(
    gap: KnowledgeGap, *, scope: FollowupScope, clock: Clock
) -> KnowledgeGap:
    if gap.scope != scope or gap not in gaps_for_context(
        (gap,), scope=scope, clock=clock
    ):
        raise ValueError("gap cannot be asked now")
    now = aware(clock.now())
    return replace(
        gap, status="asked", asked_at=now, cooldown_until=now + timedelta(days=3)
    )


def skip_gap(gap: KnowledgeGap, *, scope: FollowupScope) -> KnowledgeGap:
    if gap.scope != scope or gap.status not in {"open", "asked"}:
        raise ValueError("gap cannot be skipped")
    skips = gap.skips + 1
    return replace(gap, skips=skips, status="dismissed" if skips >= 2 else gap.status)


def pause_questions(*, clock: Clock) -> datetime:
    return aware(clock.now()) + timedelta(days=7)

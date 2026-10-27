"""Transparent importance and 180-day half-life; no implicit reading of host-local time."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock

    from .contracts import MemoryFact

BASE_IMPORTANCE = {
    "goal": 0.9,
    "constraint": 0.9,
    "event": 0.7,
    "concern": 0.7,
    "preference": 0.6,
    "background": 0.5,
    "correction": 0.8,
    "profile": 0.7,
}


def _instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("重要度计算需要带时区的时刻")
    return value.astimezone(UTC)


def decay_factor(fact: MemoryFact, *, clock: Clock, half_life_days: float = 180) -> float:
    if (
        isinstance(half_life_days, bool)
        or not isinstance(half_life_days, (float, int))
        or not math.isfinite(half_life_days)
        or half_life_days <= 0
    ):
        raise ValueError("半衰期须为正数")
    now = _instant(clock.now())
    if fact.kind in {"constraint", "goal"}:
        return 1.0
    age = max(0.0, (now - _instant(fact.said_at)).total_seconds() / 86400)
    return math.exp2(-age / half_life_days)


def importance_score(fact: MemoryFact, *, clock: Clock, half_life_days: float = 180) -> float:
    if not fact.source_valid or fact.status != "active":
        return 0.0
    base = max(fact.importance, BASE_IMPORTANCE.get(fact.kind, 0.5))
    if fact.pinned:
        base = max(base, 0.9)
    return min(1.0, max(0.0, base * decay_factor(fact, clock=clock, half_life_days=half_life_days)))

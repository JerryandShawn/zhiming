"""Rank already-authorized facts; this adapter grants no persistence or read permission."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from mingjing_core.timekit.timestamps import history_instant

from .contracts import MemoryFact
from .scoring import importance_score

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock


def finite_score(value: object, default: float = 0.0) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        return default
    return max(0.0, float(value))


def authorized_fact_importance(row: dict[str, Any], *, clock: Clock) -> float:
    """Use the original utterance time, never a later import/index creation time."""
    said_at = history_instant(row.get("said_at") or row.get("valid_from"))
    if said_at is None:
        return 0.0
    importance = min(1.0, finite_score(row.get("importance"), 0.5))
    fact = MemoryFact(
        id=row["id"],
        owner_id=row["owner"],
        subject_id=row["subject_id"],
        kind=row.get("requested_kind") or row.get("kind", "background"),
        text=row.get("content") or " ",
        source_ids=(),
        said_at=said_at,
        recorded_at=said_at,
        status="active" if row.get("status") == "active" else "retired",
        pinned=row.get("pinned") is True,
        importance=importance,
    )
    return importance_score(fact, clock=clock)


def ranked_projection(original: dict[str, Any], projected: dict[str, Any], *, clock: Clock) -> dict[str, Any]:
    """Lexical-only degradation is explicit; no vector model is loaded or inferred."""
    lexical = finite_score(projected.get("search_rank"))
    if projected.get("entity_kind") != "fact":
        return dict(projected, retrieval_score=lexical)
    importance = authorized_fact_importance(original, clock=clock)
    return dict(projected, memory_importance=importance, retrieval_score=lexical * importance)


def rank_key(row: dict[str, Any]) -> tuple[float, float, str]:
    return (
        -finite_score(row.get("retrieval_score", row.get("search_rank"))),
        -finite_score(row.get("memory_importance")),
        row["id"],
    )

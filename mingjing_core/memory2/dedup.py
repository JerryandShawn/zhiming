"""Exact semantic keys merge automatically; fuzzy overlap is only a candidate."""

import re
import unicodedata
from dataclasses import replace

from .contracts import MemoryFact


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip().rstrip("。！？!?，,；;")


def equivalent(left: MemoryFact, right: MemoryFact) -> bool:
    if (left.owner_id, left.subject_id, left.origin, left.kind, left.slot) != (
        right.owner_id,
        right.subject_id,
        right.origin,
        right.kind,
        right.slot,
    ):
        return False
    if left.status != "active" or right.status != "active" or left.valid_to is not None:
        return False
    if left.event_at != right.event_at or left.event_end != right.event_end:
        return False
    if (
        left.slot is not None
        and left.value is not None
        and right.value is not None
        and normalized(left.value) != normalized(right.value)
    ):
        return False
    return normalized(left.text) == normalized(right.text)


def merge_facts(existing: MemoryFact, incoming: MemoryFact) -> MemoryFact:
    if not equivalent(existing, incoming):
        raise ValueError("memory_merge_requires_equivalence")
    source_ids = tuple(dict.fromkeys((*existing.source_ids, *incoming.source_ids)))
    anchors = tuple(dict.fromkeys((*existing.anchors, *incoming.anchors)))
    return replace(
        existing,
        source_ids=source_ids,
        anchors=anchors,
        recorded_at=max(existing.recorded_at, incoming.recorded_at),
        importance=max(existing.importance, incoming.importance),
        pinned=existing.pinned or incoming.pinned,
        revision=existing.revision + 1,
    )

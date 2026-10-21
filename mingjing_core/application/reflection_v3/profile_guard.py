"""Pinned and hand-edited items retain the same current source guard as every other profile item."""

from datetime import datetime

from mingjing_core.memory2.contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from mingjing_core.memory2.reflection import ProfileItem
from mingjing_core.timekit.clock import Clock

from .fact_policy import select_facts
from .profile_contracts import ProfileDocument, ProfileEntry
from .validation import ReflectionError, instant, scope_snapshot


def current_profile_items(
    document: ProfileDocument,
    *,
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    current_profile_revision: int | None = None,
    settings: MemorySettings | None = None,
    confirmations: tuple[Confirmation, ...] = (),
) -> tuple[tuple[ProfileEntry, ...], tuple[str, ...], tuple[str, ...]]:
    scope_snapshot(snapshot, scope)
    if not isinstance(document, ProfileDocument) or document.scope != scope:
        raise ReflectionError("profile_scope_mismatch")
    if any(row.scope != scope for row in document.entries):
        raise ReflectionError("profile_entry_scope_mismatch")
    if (
        type(current_profile_revision) is not int
        or current_profile_revision != document.revision
        or document.snapshot_revision != snapshot.revision
        or document.source_epoch != snapshot.source_epoch
        or not document.active
    ):
        return (), tuple(row.item.id for row in document.entries), ("current_profile_snapshot_required",)
    facts, _ = select_facts(snapshot, scope=scope, clock=clock, settings=settings, confirmations=confirmations)
    current = {fact.id: fact for fact in facts}
    kept, omitted, warnings = [], [], []
    for entry in document.entries:
        reason = _entry_reason(entry, current, instant(clock.now()))
        if reason:
            omitted.append(entry.item.id)
            warnings.append(reason)
        else:
            kept.append(entry)
    return tuple(kept), tuple(omitted), tuple(dict.fromkeys(warnings))


def _entry_reason(entry: ProfileEntry, facts: dict[str, MemoryFact], now: datetime) -> str | None:
    item = entry.item
    if not entry.active:
        return "profile_item_inactive"
    if item.section == 7 or entry.origin == "chart_unverified":
        return "chart_summary_requires_authoritative_p8_contract"
    if item.updated_at is None or item.updated_at > now:
        return "profile_update_time_required"
    if not item.fact_ids or not set(item.fact_ids) <= facts.keys():
        return "profile_current_facts_required"
    selected = [facts[identity] for identity in item.fact_ids]
    sources = {identity for fact in selected for identity in fact.source_ids}
    anchors = {anchor for fact in selected for anchor in fact.anchors}
    if set(item.source_ids) != sources or not entry.anchors or set(entry.anchors) != anchors:
        return "profile_source_anchors_mismatch"
    return None


def items_only(entries: tuple[ProfileEntry, ...]) -> tuple[ProfileItem, ...]:
    return tuple(entry.item for entry in entries)

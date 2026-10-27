"""Bounded R14 contradictions, shared by proposal creation and consumption."""

from __future__ import annotations

from mingjing_core.memory.change_signals import explicit_replacement_slot, stated_city
from mingjing_core.memory.slots import SLOTS, compatible_statement, normalize_slot
from mingjing_core.memory2.conflict_candidates import opposing_preferences
from mingjing_core.memory2.dedup import normalized


def contradictory(previous: dict, incoming: str, slot: str | None = None) -> bool:
    before = previous.get("content", "")
    if normalized(before) == normalized(incoming) or explicit_replacement_slot(before, incoming):
        return False
    if opposing_preferences(before, incoming):
        return True
    old_city, new_city = stated_city(before), stated_city(incoming)
    if old_city and new_city and old_city != new_city:
        return True
    canonical = normalize_slot(slot) or normalize_slot(previous.get("slot"))
    return bool(
        canonical
        and SLOTS[canonical].cardinality == "single"
        and canonical != "preference"
        and all(compatible_statement(canonical, text) for text in (before, incoming))
        and normalize_slot(previous.get("slot")) in {None, canonical}
    )

"""Independent chains still share one current value in a registered single slot."""

from mingjing_core.memory.slots import get_slot

from .contracts import MemoryFact, MemorySnapshot
from .guards import MemoryGuardError, authorize_fact


def has_current_peer(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    *,
    updates: dict[str, MemoryFact] | None = None,
    excluded: frozenset[str] = frozenset(),
) -> bool:
    slot = get_slot(fact.slot)
    if slot is None or slot.cardinality != "single":
        return False
    replacements = updates or {}
    for previous in snapshot.facts:
        peer = replacements.get(previous.id, previous)
        if peer.id == fact.id or peer.id in excluded or peer.slot != fact.slot:
            continue
        if peer.status != "active" or peer.valid_to is not None:
            continue
        try:
            authorize_fact(peer, snapshot, snapshot.scope)
        except MemoryGuardError:
            continue
        return True
    return False

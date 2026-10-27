"""Bridge current authorized memory snapshots into the pure retrieval port."""

from mingjing_core.memory.retrieval_types import SearchSource, SearchUnit, SourceRef
from mingjing_core.timekit.clock import Clock

from .contracts import MemoryFact, MemorySnapshot, utc
from .guards import MemoryGuardError, authorize_fact


def search_sources(snapshot: MemorySnapshot) -> tuple[SearchSource, ...]:
    return tuple(
        SearchSource(
            source.id,
            source.owner_id,
            source.subject_id,
            source.revision,
            active=source.active and not source.revoked and not source.optout,
            incognito=source.incognito,
            role=source.role,
            origin=source.origin,
        )
        for source in snapshot.sources
    )


def _unit(fact: MemoryFact, valid: bool) -> SearchUnit:
    kind = "note" if fact.origin == "assistant_claim" else "event" if fact.kind == "event" else "fact"
    refs = tuple(dict.fromkeys(SourceRef(anchor.source_id, anchor.revision) for anchor in fact.anchors))
    return SearchUnit(
        fact.id,
        fact.owner_id,
        fact.subject_id,
        kind,
        fact.text,
        fact.said_at,
        fact.event_at,
        origin=fact.origin,
        source_refs=refs,
        fact_id=fact.id if kind != "note" else None,
        valid=valid,
        category=fact.kind,
    )


def search_units(snapshot: MemorySnapshot, *, clock: Clock, include_history: bool = False) -> tuple[SearchUnit, ...]:
    if type(include_history) is not bool:
        raise ValueError("历史检索开关无效")
    stamp, units = utc(clock.now()), []
    for fact in snapshot.facts:
        if fact.status not in ({"active", "archived"} if include_history else {"active"}):
            continue
        try:
            authorize_fact(fact, snapshot, snapshot.scope, allow_retired=include_history)
        except MemoryGuardError:
            continue
        current = (
            fact.status == "active"
            and fact.superseded_by is None
            and (fact.valid_from is None or fact.valid_from <= stamp)
            and (fact.valid_to is None or stamp < fact.valid_to)
        )
        if current or include_history:
            units.append(_unit(fact, current))
    return tuple(units)

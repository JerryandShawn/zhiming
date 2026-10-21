"""An explicit rule proposes priorities; it neither asks users nor silently closes excess gaps."""

from mingjing_core.memory2.contracts import MemoryFact, MemoryScope

from .validation import ReflectionError, typed_tuple
from .work_contracts import ExistingGap, GapPriorityCandidate, KnowledgeGap


def prioritize_gaps(
    existing: tuple[ExistingGap, ...],
    proposed: tuple[KnowledgeGap, ...],
    facts: tuple[MemoryFact, ...],
    scope: MemoryScope,
) -> tuple[tuple[KnowledgeGap, ...], tuple[GapPriorityCandidate, ...], tuple[str, ...]]:
    rows = typed_tuple(existing, ExistingGap)
    if any(row.scope != scope for row in rows) or len({row.id for row in rows}) != len(rows):
        raise ReflectionError("gap_scope_or_identity_invalid")
    current, accepted = {fact.id: fact for fact in facts}, []
    for row in rows:
        if not row.fact_ids or not set(row.fact_ids) <= current.keys():
            continue
        sources = {sid for identity in row.fact_ids for sid in current[identity].source_ids}
        if set(row.source_ids) == sources:
            accepted.append(row)
    open_rows = tuple(row for row in accepted if row.status in {"open", "asked"})
    known_fact_sets = {frozenset(row.fact_ids) for row in accepted}
    gaps = tuple(row for row in proposed if frozenset(row.fact_ids) not in known_fact_sets)
    # Mention counts and blocking markers are explicit host inputs, not inferred emotions.
    priorities = tuple(
        GapPriorityCandidate(row.id, row.revision, min(5, 1 + 2 * row.blocking + min(2, row.mentions)), row.source_ids)
        for row in open_rows
        if row.status == "open"
    )
    available = max(0, 15 - len(open_rows))
    notices = ("gap_capacity_requires_host_review",) if len(gaps) > available or len(open_rows) > 15 else ()
    return gaps[:available], priorities[:15], notices

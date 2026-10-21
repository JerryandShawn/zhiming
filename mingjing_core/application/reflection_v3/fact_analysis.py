"""Deterministic deduplication, date repair and contradiction suggestions remain review intentions."""

from mingjing_core.memory2.conflicts import possible_conflicts
from mingjing_core.memory2.contracts import MemoryFact, MemorySnapshot
from mingjing_core.memory2.dedup import equivalent
from mingjing_core.memory2.event_time_extended_v2 import ExtendedEventCandidate, absolute_event_candidate_extended

from .validation import digest
from .work_contracts import DuplicateCandidate, KnowledgeGap


def duplicate_candidates(facts: tuple[MemoryFact, ...]) -> tuple[DuplicateCandidate, ...]:
    remaining, groups = list(facts), []
    while remaining:
        first = remaining.pop(0)
        selected = [first, *(fact for fact in remaining if equivalent(first, fact))]
        ids = {fact.id for fact in selected}
        remaining = [fact for fact in remaining if fact.id not in ids]
        if len(selected) > 1:
            groups.append(
                DuplicateCandidate(
                    tuple(sorted(ids)),
                    tuple(sorted({source for fact in selected for source in fact.source_ids})),
                    tuple(sorted((fact.id, fact.revision) for fact in selected)),
                )
            )
    return tuple(groups)


def conflict_gaps(facts: tuple[MemoryFact, ...]) -> tuple[KnowledgeGap, ...]:
    result = []
    ordered = sorted(facts, key=lambda row: (row.said_at, row.id))
    for index, fact in enumerate(ordered):
        for conflict in possible_conflicts(fact, tuple(ordered[:index])):
            old = next(row for row in ordered if row.id == conflict.old_id)
            sources = tuple(sorted(set(old.source_ids) | set(fact.source_ids)))
            result.append(gap("possible_conflict", conflict.proposal, (old.id, fact.id), sources))
    return tuple(result)


def date_candidates(
    facts: tuple[MemoryFact, ...],
    snapshot: MemorySnapshot,
    timezone: str,
) -> tuple[tuple[ExtendedEventCandidate, ...], tuple[KnowledgeGap, ...]]:
    repairs, gaps = [], []
    for fact in facts:
        if fact.kind != "event" or fact.event_at is not None:
            continue
        candidate = absolute_event_candidate_extended(fact, snapshot, tz=timezone)
        if candidate.projected is not None and not candidate.needs_clarification:
            repairs.append(candidate)
        else:
            gaps.append(
                gap(
                    "event_date_requires_clarification",
                    "这件事的具体日期或时间范围是什么？",
                    (fact.id,),
                    fact.source_ids,
                )
            )
    return tuple(repairs), tuple(gaps)


def gap(reason: str, question: str, fact_ids: tuple[str, ...], source_ids: tuple[str, ...]) -> KnowledgeGap:
    identity = digest([reason, list(fact_ids), list(source_ids)])
    return KnowledgeGap("gap:" + identity, reason, question, fact_ids, source_ids)

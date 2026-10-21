"""Injected extraction candidates pass the frozen write policy but are never applied here."""

from mingjing_core.memory2.conflicts import possible_conflicts
from mingjing_core.memory2.contracts import (
    Confirmation,
    MemoryFact,
    MemoryScope,
    MemorySettings,
    MemorySnapshot,
    PolicyDecision,
)
from mingjing_core.memory2.dedup import equivalent
from mingjing_core.memory2.sensitivity import decide_policy
from mingjing_core.timekit.clock import Clock

from .fact_analysis import gap
from .fact_policy import confirmation_for
from .validation import ReflectionError, opaque, typed_tuple
from .work_contracts import FactCandidate, KnowledgeGap, WorkOmission


def check_extracted_candidates(
    values: tuple[MemoryFact, ...],
    *,
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings,
    confirmations: tuple[Confirmation, ...],
    thread_source_ids: tuple[str, ...],
    known_facts: tuple[MemoryFact, ...],
) -> tuple[tuple[FactCandidate, ...], tuple[WorkOmission, ...], tuple[KnowledgeGap, ...]]:
    candidates = typed_tuple(values, MemoryFact)
    if any((row.owner_id, row.subject_id) != (scope.owner_id, scope.subject_id) for row in candidates):
        raise ReflectionError("extracted_candidate_scope_mismatch")
    result, omitted, gaps = [], [], []
    seen = set()
    for fact in candidates:
        opaque(fact.id, *fact.source_ids)
        if fact.id in seen:
            raise ReflectionError("duplicate_extracted_candidate")
        seen.add(fact.id)
        if not set(fact.source_ids) <= set(thread_source_ids):
            omitted.append(WorkOmission(fact.id, "extracted_source_not_in_thread"))
            continue
        if (
            fact.origin != "user"
            or fact.kind in {"note", "assistant_claim", "chart_summary", "chart_interpretation"}
            or snapshot.fact(fact.id) is not None
        ):
            omitted.append(WorkOmission(fact.id, "not_a_missing_user_fact"))
            continue
        decision = _policy(fact, snapshot, scope, clock, settings, confirmations)
        if decision is None:
            omitted.append(WorkOmission(fact.id, "extracted_source_unavailable"))
            continue
        if decision.action in {"stop", "reject"}:
            omitted.append(WorkOmission(fact.id, "extracted_policy_" + decision.action))
        elif decision.action == "save" and any(equivalent(current, fact) for current in known_facts):
            omitted.append(WorkOmission(fact.id, "fact_already_represented"))
        elif decision.action == "save" and (conflicts := possible_conflicts(fact, known_facts)):
            for conflict in conflicts:
                old = next(row for row in known_facts if row.id == conflict.old_id)
                sources = tuple(sorted(set(old.source_ids) | set(fact.source_ids)))
                gaps.append(gap("possible_conflict", conflict.proposal, (old.id, fact.id), sources))
            omitted.append(WorkOmission(fact.id, "extracted_possible_conflict"))
        else:
            result.append(FactCandidate(fact, decision.action, decision.action != "save", decision.reason))
    return tuple(result), tuple(omitted), tuple(gaps)


def _policy(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings,
    confirmations: tuple[Confirmation, ...],
) -> PolicyDecision | None:
    try:
        return decide_policy(
            snapshot,
            fact,
            scope=scope,
            clock=clock,
            settings=settings,
            confirmation=confirmation_for(fact, confirmations),
        )
    except ValueError:
        return None

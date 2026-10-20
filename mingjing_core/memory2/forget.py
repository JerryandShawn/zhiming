"""Forget detaches both chain directions and scrubs the current fact projection."""

from dataclasses import replace

from .contracts import MemoryFact, MemoryScope, MemorySnapshot
from .current_guard import has_current_peer
from .guards import MemoryGuardError, authorize_fact
from .mutation_contracts import FactChange, MutationConflict, MutationPlan
from .plan_builder import seal


def plan_forget(snapshot: MemorySnapshot, fact_id: str, *, scope: MemoryScope, operation_id: str) -> MutationPlan:
    if snapshot.scope != scope:
        raise MemoryGuardError("scope_mismatch")
    fact = snapshot.fact(fact_id)
    if fact is None or (fact.owner_id, fact.subject_id) != (scope.owner_id, scope.subject_id):
        raise MutationConflict("fact_not_found")
    deleted = replace(
        fact,
        text="已遗忘",
        value=None,
        source_ids=(),
        anchors=(),
        status="deleted",
        source_valid=False,
        supersedes=None,
        superseded_by=None,
        revision=fact.revision + 1,
    )
    changes = [FactChange(fact.id, fact, deleted)]
    for neighbor in snapshot.facts:
        if neighbor.id == fact.id or (neighbor.owner_id, neighbor.subject_id) != (scope.owner_id, scope.subject_id):
            continue
        values = {}
        if neighbor.supersedes == fact.id:
            values["supersedes"] = None
        if neighbor.superseded_by == fact.id:
            values["superseded_by"] = None
            if (
                fact.superseded_by is None
                and _available(neighbor, snapshot)
                and not has_current_peer(neighbor, snapshot, excluded=frozenset({fact.id}))
            ):
                values["valid_to"] = None
        if values:
            changed = replace(neighbor, **values, revision=neighbor.revision + 1)
            changes.append(FactChange(neighbor.id, neighbor, changed))
    return seal(
        MutationPlan(
            operation_id,
            scope,
            snapshot.revision,
            snapshot.source_epoch,
            tuple(changes),
            "forgotten",
            "已遗忘，并安全更新关联记录。",
            policy_action="forget",
        )
    )


def _available(fact: MemoryFact, snapshot: MemorySnapshot) -> bool:
    if fact.status != "active" or not fact.source_valid:
        return False
    try:
        authorize_fact(fact, snapshot, snapshot.scope)
    except MemoryGuardError:
        return False
    return True

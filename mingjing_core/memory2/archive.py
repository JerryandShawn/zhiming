"""C2 expiration produces reversible archive metadata, never data deletion."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import TYPE_CHECKING

from .contracts import utc
from .guards import MemoryGuardError, authorize_fact
from .mutation_contracts import FactChange

if TYPE_CHECKING:
    from mingjing_core.timekit.clock import Clock

    from .contracts import MemoryScope, MemorySnapshot
    from .mutation_contracts import MutationPlan


def archive_changes(snapshot: MemorySnapshot, *, scope: MemoryScope, clock: Clock) -> tuple[FactChange, ...]:
    if snapshot.scope != scope:
        raise MemoryGuardError("scope_mismatch")
    now = utc(clock.now())
    result = []
    for fact in snapshot.facts:
        deadlines = [value for value in (fact.valid_to, fact.event_end) if value is not None]
        if fact.status != "active" or not deadlines or min(deadlines) > now:
            continue
        if fact.said_at > now or fact.recorded_at > now:
            continue
        try:
            authorize_fact(fact, snapshot, scope)
        except MemoryGuardError:
            continue
        after = replace(fact, status="archived", revision=fact.revision + 1)
        result.append(FactChange(fact.id, fact, after))
    return tuple(result)


def plan_archives(
    snapshot: MemorySnapshot, *, scope: MemoryScope, clock: Clock, operation_id: str | None = None
) -> MutationPlan:
    from .mutations import plan_changes

    changes = archive_changes(snapshot, scope=scope, clock=clock)
    if operation_id is None:
        fingerprint = repr((scope, snapshot.revision, [(item.id, item.before.revision) for item in changes]))
        operation_id = "memory-archive:" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return plan_changes(
        snapshot,
        changes,
        scope=scope,
        operation_id=operation_id,
        write_status="archived",
        summary="已生成到期记忆归档计划，可撤销。",
    )

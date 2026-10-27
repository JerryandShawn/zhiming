"""Expiration and future-event work are metadata candidates; no archive or notification is performed."""

from mingjing_core.memory2.archive import archive_changes
from mingjing_core.memory2.contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from mingjing_core.timekit.clock import Clock

from .fact_policy import fact_reason
from .validation import instant
from .work_contracts import ArchiveCandidate, FollowupCandidate


def lifecycle_candidates(
    facts: tuple[MemoryFact, ...],
    snapshot: MemorySnapshot,
    *,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings,
    confirmations: tuple[Confirmation, ...],
) -> tuple[tuple[ArchiveCandidate, ...], tuple[FollowupCandidate, ...]]:
    archives = []
    for change in archive_changes(snapshot, scope=scope, clock=clock):
        fact = change.before
        if fact_reason(fact, snapshot, scope, clock, settings, confirmations, include_expired=True) is not None:
            continue
        deadline = min(value for value in (fact.valid_to, fact.event_end) if value is not None)
        archives.append(ArchiveCandidate(fact.id, fact.revision, fact.source_ids, deadline))
    now = instant(clock.now())
    followups = tuple(
        FollowupCandidate(fact.id, fact.revision, fact.source_ids, fact.event_at, fact.event_end)
        for fact in facts
        if fact.kind == "event" and fact.event_at is not None and fact.event_at > now
    )
    return tuple(archives), followups

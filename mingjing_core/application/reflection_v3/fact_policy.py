"""Current authorizations and sensitive consent precede every derived profile or work candidate."""

from dataclasses import dataclass

from mingjing_core.memory.slots import get_slot
from mingjing_core.memory2.contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from mingjing_core.memory2.guards import MemoryGuardError, authorize_fact
from mingjing_core.memory2.sensitivity import decide_policy
from mingjing_core.timekit.clock import Clock

from .validation import ReflectionError, instant, opaque, scope_snapshot, typed_tuple


@dataclass(frozen=True)
class FactOmission:
    fact_id: str
    reason: str


def confirmation_for(fact: MemoryFact, confirmations: tuple[Confirmation, ...]) -> Confirmation | None:
    matching = [
        row
        for row in confirmations
        if any(
            row.source_id == anchor.source_id
            and row.source_revision == anchor.revision
            and row.quote_fingerprint == anchor.quote_fingerprint
            for anchor in fact.anchors
        )
    ]
    return next((row for row in matching if row.decision == "declined"), matching[0] if matching else None)


def fact_reason(
    fact: MemoryFact,
    snapshot: MemorySnapshot,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings,
    confirmations: tuple[Confirmation, ...],
    *,
    include_expired: bool = False,
) -> str | None:
    now = instant(clock.now())
    if fact.origin != "user" or fact.kind in {"note", "assistant_claim", "chart_summary", "chart_interpretation"}:
        return "assistant_or_inferred_is_not_user_fact"
    if fact.said_at > now or fact.recorded_at > now:
        return "fact_time_in_future"
    if fact.valid_from is not None and fact.valid_from > now:
        return "fact_not_yet_valid"
    if not include_expired and any(value is not None and value <= now for value in (fact.valid_to, fact.event_end)):
        return "fact_expired"
    try:
        authorize_fact(fact, snapshot, scope)
        policy = decide_policy(
            snapshot,
            fact,
            scope=scope,
            clock=clock,
            settings=settings,
            confirmation=confirmation_for(fact, confirmations),
        )
    except MemoryGuardError:
        return "fact_source_unavailable"
    return None if policy.action == "save" else "fact_policy_" + policy.action


def select_facts(
    snapshot: MemorySnapshot,
    *,
    scope: MemoryScope,
    clock: Clock,
    settings: MemorySettings | None = None,
    confirmations: tuple[Confirmation, ...] = (),
) -> tuple[tuple[MemoryFact, ...], tuple[FactOmission, ...]]:
    scope_snapshot(snapshot, scope)
    if settings is not None and not isinstance(settings, MemorySettings):
        raise ReflectionError("memory_settings_required")
    consent = typed_tuple(confirmations, Confirmation)
    if any(row.scope != scope for row in consent):
        raise ReflectionError("confirmation_scope_mismatch")
    eligible, omitted = [], []
    for fact in snapshot.facts:
        opaque(fact.id, *fact.source_ids)
        reason = fact_reason(fact, snapshot, scope, clock, settings or MemorySettings(), consent)
        if reason:
            omitted.append(FactOmission(fact.id, reason))
        else:
            eligible.append(fact)
    singles: dict[str, list[MemoryFact]] = {}
    for fact in eligible:
        slot = get_slot(fact.slot, fact.text)
        if slot is not None and slot.cardinality == "single":
            singles.setdefault(slot.name, []).append(fact)
    invalid = {fact.id for values in singles.values() if len(values) > 1 for fact in values}
    omitted.extend(FactOmission(identity, "multiple_current_single_slot") for identity in sorted(invalid))
    return tuple(fact for fact in eligible if fact.id not in invalid), tuple(omitted)

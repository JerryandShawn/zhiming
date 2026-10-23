"""Create immutable plans; source authentication and sensitivity are intrinsic."""

import json
from dataclasses import asdict, replace
from datetime import datetime
from hashlib import sha256

from mingjing_core.memory.slots import get_slot, normalize_slot, residence_value_asserted
from mingjing_core.timekit.clock import Clock

from .conflicts import possible_conflicts
from .contracts import Confirmation, MemoryFact, MemoryScope, MemorySettings, MemorySnapshot
from .dedup import equivalent, merge_facts
from .guards import MemoryGuardError, authorize_fact
from .mutation_contracts import FactChange, MutationConflict, MutationPlan


def fingerprint(plan: MutationPlan) -> str:
    content = asdict(replace(plan, fingerprint=""))
    raw = json.dumps(content, sort_keys=True, default=_json_value, ensure_ascii=False, separators=(",", ":"))
    return sha256(raw.encode("utf-8")).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise ValueError("memory_plan_value_invalid")


def seal(plan: MutationPlan) -> MutationPlan:
    if not plan.operation_id:
        raise MutationConflict("operation_id_required")
    return replace(plan, fingerprint=fingerprint(plan))


def plan_changes(
    snapshot: MemorySnapshot,
    changes: tuple[FactChange, ...],
    *,
    scope: MemoryScope,
    operation_id: str,
    write_status: str = "archived",
    summary: str = "",
) -> MutationPlan:
    if snapshot.scope != scope:
        raise MemoryGuardError("scope_mismatch")
    for change in changes:
        if change.before is None or change.after is None:
            raise MutationConflict("metadata_plan_requires_existing_fact")
        if (change.before.owner_id, change.before.subject_id) != (scope.owner_id, scope.subject_id):
            raise MemoryGuardError("scope_mismatch")
        safe = replace(change.before, status=change.after.status, revision=change.after.revision)
        if safe != change.after or change.after.status not in {"archived", "retired"}:
            raise MutationConflict("metadata_plan_cannot_change_fact_content")
    return seal(
        MutationPlan(
            operation_id, scope, snapshot.revision, snapshot.source_epoch, tuple(changes), write_status, summary
        )
    )


def plan_write(
    snapshot: MemorySnapshot,
    incoming: MemoryFact,
    *,
    scope: MemoryScope,
    operation_id: str,
    clock: Clock,
    settings: MemorySettings | None = None,
    confirmation: Confirmation | None = None,
    model_hint: tuple[str, ...] = (),
) -> MutationPlan:
    from .sensitivity import decide_policy

    settings = settings or MemorySettings()
    incoming = replace(incoming, slot=normalize_slot(incoming.slot, incoming.text))
    if incoming.slot == "residence_city" and not residence_value_asserted(incoming.text, incoming.value):
        incoming = replace(incoming, slot=None)
    decision = decide_policy(
        snapshot,
        incoming,
        scope=scope,
        clock=clock,
        settings=settings,
        confirmation=confirmation,
        model_hint=model_hint,
    )
    base = MutationPlan(
        operation_id,
        scope,
        snapshot.revision,
        snapshot.source_epoch,
        write_status=decision.action,
        question_key=decision.question_key,
        incoming=incoming,
        settings=settings,
        confirmation=confirmation,
        model_hint=tuple(model_hint),
        evaluated_at=clock.now(),
        policy_action=decision.action,
    )
    if decision.action != "save":
        return seal(base)
    authorize_fact(incoming, snapshot, scope)
    if incoming.origin != "user":
        return seal(replace(base, write_status="reject", policy_action="reject"))
    if snapshot.fact(incoming.id) is not None:
        raise MutationConflict("fact_id_already_exists")
    changes, status, summary = _write_changes(snapshot, incoming)
    return seal(replace(base, changes=changes, write_status=status, summary=summary))


def _write_changes(snapshot: MemorySnapshot, incoming: MemoryFact) -> tuple[tuple[FactChange, ...], str, str]:
    active = tuple(fact for fact in snapshot.facts if _eligible(fact, snapshot))
    match = next((fact for fact in active if equivalent(fact, incoming)), None)
    if match is not None:
        merged = merge_facts(match, incoming)
        return (FactChange(match.id, match, merged),), "merged", "已合并相同记录，并保留全部来源。"
    slot = get_slot(incoming.slot, incoming.text)
    previous = [fact for fact in active if fact.slot == incoming.slot and fact.valid_to is None]
    if slot is not None and slot.cardinality == "single" and previous:
        old = max(previous, key=lambda fact: fact.said_at)
        return _single_slot(old, incoming)
    conflicts = possible_conflicts(incoming, active)
    if conflicts:
        return (), "possible_conflict", conflicts[0].proposal
    return (FactChange(incoming.id, None, incoming),), "saved", "已记住，可随时撤销。"


def _eligible(fact: MemoryFact, snapshot: MemorySnapshot) -> bool:
    try:
        authorize_fact(fact, snapshot, snapshot.scope)
    except MemoryGuardError:
        return False
    return True


def _single_slot(old: MemoryFact, incoming: MemoryFact) -> tuple[tuple[FactChange, ...], str, str]:
    if incoming.said_at <= old.said_at or incoming.value is None or old.value is None:
        return (), "possible_conflict", f"以前你说“{old.text}”，现在说“{incoming.text}”，以哪个为准？"
    before = replace(old, valid_to=incoming.said_at, superseded_by=incoming.id, revision=old.revision + 1)
    after = replace(incoming, supersedes=old.id)
    return (
        (FactChange(old.id, old, before), FactChange(after.id, None, after)),
        "updated",
        (f"已更新：{old.value} → {after.value}。原记录保留在历史中，可撤销。"),
    )

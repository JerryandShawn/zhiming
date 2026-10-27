"""Undo only matching fields; revoked origins and later edits never revive."""

from dataclasses import fields, replace
from hashlib import sha256

from .contracts import MemoryFact, MemorySnapshot, OperationRecord
from .current_guard import has_current_peer
from .guards import MemoryGuardError, authorize_fact
from .mutation_contracts import MutationConflict, MutationOutcome, MutationPlan
from .plan_builder import fingerprint


def undo_plan(snapshot: MemorySnapshot, plan: MutationPlan, *, operation_id: str) -> MutationOutcome:
    if snapshot.scope != plan.scope or fingerprint(plan) != plan.fingerprint or not operation_id:
        raise MutationConflict("undo_plan_invalid")
    if plan.policy_action == "forget":
        raise MutationConflict("forgotten_content_cannot_be_restored")
    digest = sha256(f"undo:{plan.operation_id}:{plan.fingerprint}".encode()).hexdigest()
    prior_undo = next((record for record in snapshot.operations if record.operation_id == operation_id), None)
    if prior_undo:
        if prior_undo.fingerprint != digest:
            raise MutationConflict("operation_payload_changed")
        return MutationOutcome(snapshot, "undone", fact_ids=prior_undo.result_ids, replayed=True)
    prior = next((record for record in snapshot.operations if record.operation_id == plan.operation_id), None)
    if prior is None or prior.fingerprint != plan.fingerprint:
        raise MutationConflict("operation_not_applied")
    if prior.status == "undone":
        return MutationOutcome(snapshot, "undone", fact_ids=prior.result_ids, replayed=True)
    facts, conflicts = _restore_facts(snapshot, plan)
    records = tuple(replace(record, status="undone") if record == prior else record for record in snapshot.operations)
    record = OperationRecord(operation_id, digest, result_ids=prior.result_ids, undo_of=plan.operation_id)
    result = replace(snapshot, facts=facts, operations=(*records, record), revision=snapshot.revision + 1)
    return MutationOutcome(result, "undone", "已撤销；后续修改和失效来源保留保护。", prior.result_ids, conflicts)


def _restore_facts(snapshot: MemorySnapshot, plan: MutationPlan) -> tuple[tuple[MemoryFact, ...], tuple[str, ...]]:
    updates, conflicts = {}, []
    blocked = _blocked_predecessors(snapshot, plan)
    for change in plan.changes:
        current = snapshot.fact(change.id)
        if current is None or current.status == "deleted" or not current.source_valid:
            conflicts.append(f"{change.id}.unavailable")
            continue
        if change.before is None:
            if current == change.after:
                updates[current.id] = replace(current, status="retired", revision=current.revision + 1)
            else:
                conflicts.append(f"{change.id}.later_changes")
            continue
        restored, skipped = _restore_fields(current, change.before, change.after)
        if current.id in blocked:
            restored = replace(
                restored, valid_to=current.valid_to, superseded_by=current.superseded_by, revision=current.revision
            )
            skipped.append(f"{current.id}.later_successor")
        try:
            if restored.status == "active":
                authorize_fact(restored, snapshot, plan.scope)
        except MemoryGuardError:
            conflicts.append(f"{change.id}.source_unavailable")
            continue
        updates[current.id] = restored
        conflicts.extend(skipped)
    _protect_reopening(snapshot, updates, conflicts)
    return tuple(updates.get(fact.id, fact) for fact in snapshot.facts), tuple(conflicts)


def _protect_reopening(snapshot: MemorySnapshot, updates: dict[str, MemoryFact], conflicts: list[str]) -> None:
    blocked = []
    for fact in updates.values():
        current = snapshot.fact(fact.id)
        reopening = current is not None and (current.valid_to is not None or current.status != "active")
        if (
            reopening
            and fact.status == "active"
            and fact.valid_to is None
            and has_current_peer(fact, snapshot, updates=updates)
        ):
            blocked.append(fact.id)
    for fact_id in blocked:
        current, restored = snapshot.fact(fact_id), updates[fact_id]
        updates[fact_id] = replace(
            restored,
            status=current.status,
            valid_to=current.valid_to,
            superseded_by=current.superseded_by,
            revision=current.revision,
        )
        conflicts.append(f"{fact_id}.other_current")


def _blocked_predecessors(snapshot: MemorySnapshot, plan: MutationPlan) -> set[str]:
    blocked = set()
    for change in plan.changes:
        if change.before is not None or change.after is None or change.after.supersedes is None:
            continue
        current = snapshot.fact(change.id)
        if current != change.after:
            blocked.add(change.after.supersedes)
    return blocked


def _restore_fields(current: MemoryFact, before: MemoryFact, after: MemoryFact) -> tuple[MemoryFact, list[str]]:
    values, conflicts = {}, []
    for item in fields(MemoryFact):
        old, applied, now = getattr(before, item.name), getattr(after, item.name), getattr(current, item.name)
        if old == applied:
            continue
        if now == applied:
            values[item.name] = old
        else:
            conflicts.append(f"{current.id}.{item.name}")
    return replace(current, **values), conflicts

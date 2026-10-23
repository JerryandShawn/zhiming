"""Pure revision-checked application; no database or model calls are made."""

from dataclasses import replace

from mingjing_core.timekit.clock import Clock, FrozenClock

from .contracts import MemorySnapshot, OperationRecord
from .guards import MemoryGuardError, authorize_fact
from .mutation_contracts import MutationConflict, MutationOutcome, MutationPlan
from .plan_builder import fingerprint, plan_changes, plan_write

__all__ = ["apply_plan", "plan_changes", "plan_write"]


def apply_plan(snapshot: MemorySnapshot, plan: MutationPlan, *, clock: Clock | None = None) -> MutationOutcome:
    if snapshot.scope != plan.scope or not plan.fingerprint or fingerprint(plan) != plan.fingerprint:
        raise MutationConflict("mutation_plan_invalid")
    prior = next((record for record in snapshot.operations if record.operation_id == plan.operation_id), None)
    if prior is not None:
        if prior.fingerprint != plan.fingerprint:
            raise MutationConflict("operation_payload_changed")
        status = "undone" if prior.status == "undone" else _replay_status(snapshot, plan, prior)
        return MutationOutcome(snapshot, status, fact_ids=prior.result_ids, replayed=True)
    if snapshot.revision != plan.expected_revision or snapshot.source_epoch != plan.source_epoch:
        raise MutationConflict("snapshot_revision_changed")
    _validate_policy(snapshot, plan, clock)
    for change in plan.changes:
        if snapshot.fact(change.id) != change.before:
            raise MutationConflict("fact_revision_changed")
        if change.after is None or change.after.id != change.id:
            raise MutationConflict("fact_change_invalid")
        restore = change.before is None or change.before.valid_to != change.after.valid_to
        if change.after.status == "active" and (plan.policy_action != "forget" or restore):
            authorize_fact(change.after, snapshot, plan.scope)
    updates = {change.id: change.after for change in plan.changes}
    facts = tuple(updates.pop(fact.id, fact) for fact in snapshot.facts) + tuple(updates.values())
    ids = tuple(change.id for change in plan.changes)
    record = OperationRecord(plan.operation_id, plan.fingerprint, result_ids=ids)
    questions = tuple(dict.fromkeys((*snapshot.asked_keys, *((plan.question_key,) if plan.question_key else ()))))
    result = replace(
        snapshot,
        facts=facts,
        operations=(*snapshot.operations, record),
        asked_keys=questions,
        revision=snapshot.revision + 1,
    )
    return MutationOutcome(result, plan.write_status, plan.summary, ids)


def _replay_status(snapshot: MemorySnapshot, plan: MutationPlan, prior: OperationRecord) -> str:
    for fact_id in prior.result_ids:
        fact = snapshot.fact(fact_id)
        if fact is None or fact.status == "deleted":
            if plan.write_status != "forgotten":
                return "unavailable"
            continue
        if fact.status == "active":
            try:
                authorize_fact(fact, snapshot, plan.scope)
            except MemoryGuardError:
                return "unavailable"
    return plan.write_status


def _validate_policy(snapshot: MemorySnapshot, plan: MutationPlan, clock: Clock | None) -> None:
    if plan.incoming is None:
        if plan.policy_action == "metadata":
            checked = plan_changes(
                snapshot,
                plan.changes,
                scope=plan.scope,
                operation_id=plan.operation_id,
                write_status=plan.write_status,
                summary=plan.summary,
            )
            if checked.changes != plan.changes:
                raise MutationConflict("metadata_plan_invalid")
        elif plan.policy_action == "forget":
            _validate_forget(snapshot, plan)
        else:
            raise MutationConflict("mutation_authorization_required")
        return
    from .sensitivity import decide_policy

    if plan.evaluated_at is None:
        raise MutationConflict("policy_time_required")
    decision = decide_policy(
        snapshot,
        plan.incoming,
        scope=plan.scope,
        clock=clock or FrozenClock(plan.evaluated_at),
        settings=plan.settings,
        confirmation=plan.confirmation,
        model_hint=plan.model_hint,
    )
    if decision.action != plan.policy_action or (plan.changes and decision.action != "save"):
        raise MemoryGuardError("memory_policy_changed")
    if plan.incoming.origin != "user" and plan.changes:
        raise MemoryGuardError("assistant_cannot_be_user_fact")
    checked = plan_write(
        snapshot,
        plan.incoming,
        scope=plan.scope,
        operation_id=plan.operation_id,
        clock=clock or FrozenClock(plan.evaluated_at),
        settings=plan.settings,
        confirmation=plan.confirmation,
        model_hint=plan.model_hint,
    )
    if checked.changes != plan.changes or checked.write_status != plan.write_status:
        raise MemoryGuardError("mutation_content_not_authorized")


def _validate_forget(snapshot: MemorySnapshot, plan: MutationPlan) -> None:
    from .forget import plan_forget

    deleted = [change for change in plan.changes if change.after is not None and change.after.status == "deleted"]
    if len(deleted) != 1:
        raise MutationConflict("forget_plan_invalid")
    checked = plan_forget(snapshot, deleted[0].id, scope=plan.scope, operation_id=plan.operation_id)
    if checked.changes != plan.changes:
        raise MutationConflict("forget_plan_invalid")

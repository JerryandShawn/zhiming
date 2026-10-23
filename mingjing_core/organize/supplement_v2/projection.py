"""Copy-only preview and inverse preview. Nothing here applies to a real datastore."""

from dataclasses import replace

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import FieldChange, FieldValue

from .contracts import LABEL_FIELDS, ProjectionOperation, ReviewApproval, SupplementConflict, SupplementSnapshot
from .guards import (
    authorize_entity,
    authorize_topic,
    entity_sensitivity,
    evidence_fingerprint,
    require_approval,
    require_scope,
    topic_fingerprint,
)
from .lifecycle import plan_archive_review
from .plan_contracts import RecordGuard, ReviewProposal, SupplementPlan, TopicArchiveProposal, plan_fingerprint
from .review import plan_review_labels, require_sensitive_grant


def _verify(snapshot: SupplementSnapshot, plan: SupplementPlan, scope: MemoryScope) -> None:
    require_scope(snapshot, scope)
    if not isinstance(plan, SupplementPlan) or plan.scope != scope or plan.fingerprint != plan_fingerprint(plan):
        raise SupplementConflict("plan_fingerprint_mismatch")
    if snapshot.source_epoch != plan.source_epoch:
        raise SupplementConflict("source_epoch_changed")
    if len({(guard.collection, guard.id) for guard in plan.guards}) != len(plan.guards):
        raise SupplementConflict("duplicate_record_guard")
    if len({(op.collection, op.entity_id, op.field) for op in plan.ops}) != len(plan.ops):
        raise SupplementConflict("duplicate_field_operation")
    guards = {(guard.collection, guard.id): guard for guard in plan.guards}
    for op in plan.ops:
        if (op.collection, op.entity_id) not in guards:
            raise SupplementConflict("record_guard_required")
        if op.collection == "entities" and op.field not in LABEL_FIELDS:
            raise SupplementConflict("label_only_operation_required")
        if op.collection not in {"entities", "topics"} or (op.collection == "topics" and op.field != "status"):
            raise SupplementConflict("operation_field_forbidden")
        if op.collection == "topics" and (op.before.value, op.after.value) != ("open", "archived"):
            raise SupplementConflict("archive_only_operation_required")
    for guard in plan.guards:
        _verify_guard(snapshot, guard, plan, scope)
    _review_origin(snapshot, plan, scope)


def _verify_guard(snapshot: SupplementSnapshot, guard: RecordGuard, plan: SupplementPlan, scope: MemoryScope) -> None:
    if guard.collection == "entities":
        entity = snapshot.entity(guard.id)
        if entity is None:
            raise SupplementConflict("entity_missing")
        authorize_entity(entity, snapshot, scope)
        fingerprint = evidence_fingerprint(entity)
        if any(op.collection == "entities" and op.entity_id == entity.id for op in plan.ops):
            require_sensitive_grant(entity, entity_sensitivity(entity), plan.sensitive_grants, scope)
    elif guard.collection == "topics":
        entity = snapshot.topic(guard.id)
        if entity is None:
            raise SupplementConflict("topic_missing")
        authorize_topic(entity, snapshot, scope)
        fingerprint = topic_fingerprint(entity)
    else:
        raise SupplementConflict("record_guard_invalid")
    if entity.revision != guard.revision or fingerprint != guard.evidence_fingerprint:
        raise SupplementConflict("record_evidence_changed")


def _read(snapshot: SupplementSnapshot, op: FieldChange) -> FieldValue:
    if op.collection == "entities":
        return FieldValue.read(dict(snapshot.entity(op.entity_id).labels), op.field)
    return FieldValue(True, '"' + snapshot.topic(op.entity_id).status + '"')


def _write(snapshot: SupplementSnapshot, ops: tuple[FieldChange, ...]) -> SupplementSnapshot:
    result = snapshot
    for op in ops:
        if _read(result, op) != op.before:
            raise SupplementConflict("field_precondition_changed")
        if op.collection == "entities":
            entity = result.entity(op.entity_id)
            desired = dict(entity.labels)
            if op.after.present:
                desired[op.field] = op.after.value
            else:
                desired.pop(op.field, None)
            entities = tuple(
                replace(item, labels=desired) if item.id == entity.id else item for item in result.entities
            )
            result = replace(result, entities=entities)
        else:
            topics = tuple(
                replace(item, status=op.after.value) if item.id == op.entity_id else item for item in result.topics
            )
            result = replace(result, topics=topics)
    return result


def _review_origin(snapshot: SupplementSnapshot, plan: SupplementPlan, scope: MemoryScope) -> None:
    previous = next((item for item in snapshot.operations if item.id == plan.operation_id), None)
    original = _write(snapshot, plan.inverse_ops) if previous is not None and previous.state == "applied" else snapshot
    original = replace(
        original,
        revision=plan.expected_revision,
        operations=tuple(item for item in original.operations if item.id != plan.operation_id),
    )
    # This receipt reconstructs semantics only; project_plan separately verifies the real host approval.
    receipt = ReviewApproval(scope, plan.review_fingerprint)
    if isinstance(plan.reviewed, ReviewProposal):
        expected = plan_review_labels(
            original,
            plan.reviewed,
            scope=scope,
            approval=receipt,
            sensitive_grants=plan.sensitive_grants,
        )
    elif isinstance(plan.reviewed, TopicArchiveProposal):
        expected = plan_archive_review(original, plan.reviewed, scope=scope, approval=receipt)
    else:
        raise SupplementConflict("reviewed_proposal_required")
    if expected != plan:
        raise SupplementConflict("plan_differs_from_reviewed_proposal")


def project_plan(
    snapshot: SupplementSnapshot,
    plan: SupplementPlan,
    *,
    scope: MemoryScope,
    approval: ReviewApproval,
) -> SupplementSnapshot:
    _verify(snapshot, plan, scope)
    require_approval(approval, scope, plan.review_fingerprint)
    previous = next((item for item in snapshot.operations if item.id == plan.operation_id), None)
    if previous is not None:
        if previous.fingerprint != plan.fingerprint or previous.state != "applied":
            raise SupplementConflict("operation_replay_mismatch")
        return snapshot
    if snapshot.revision != plan.expected_revision:
        raise SupplementConflict("snapshot_revision_changed")
    result = _write(snapshot, plan.ops)
    return replace(
        result,
        revision=snapshot.revision + 1,
        operations=(*snapshot.operations, ProjectionOperation(plan.operation_id, plan.fingerprint)),
    )


def project_undo(snapshot: SupplementSnapshot, plan: SupplementPlan, *, scope: MemoryScope) -> SupplementSnapshot:
    _verify(snapshot, plan, scope)
    previous = next((item for item in snapshot.operations if item.id == plan.operation_id), None)
    if previous is None or previous.fingerprint != plan.fingerprint:
        raise SupplementConflict("operation_not_applied")
    if previous.state == "undone":
        return snapshot
    if snapshot.revision != plan.expected_revision + 1:
        raise SupplementConflict("undo_snapshot_revision_changed")
    result = _write(snapshot, plan.inverse_ops)
    operations = tuple(
        replace(item, state="undone") if item.id == plan.operation_id else item for item in result.operations
    )
    return replace(result, revision=snapshot.revision + 1, operations=operations)

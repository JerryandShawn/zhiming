"""Inverse intentions require a host applied ledger and current source/field prerequisites."""

from typing import Any

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import FieldValue, digest
from mingjing_core.timekit.clock import Clock

from .contracts import DryRunConflict, DryRunPlan, ExportSnapshot, UndoPreview
from .guards import check_anchor, immutable_row, require_snapshot, row_reason
from .preview import validate_plan


def plan_undo_dry_run(plan: DryRunPlan, *, snapshot: ExportSnapshot, scope: MemoryScope, clock: Clock) -> UndoPreview:
    document = require_snapshot(snapshot, scope)
    validate_plan(plan, scope)
    ledger = next((item for item in snapshot.operations if item.operation_id == plan.operation_id), None)
    reason = None
    if ledger is None or (ledger.input_fingerprint, ledger.plan_fingerprint) != (
        plan.input_fingerprint,
        plan.fingerprint,
    ):
        reason = "applied_ledger_required"
    elif ledger.state == "planned":
        reason = "batch_not_applied"
    elif ledger.state == "applied" and ledger.applied_revision <= plan.expected_revision:
        reason = "applied_revision_not_after_plan"
    elif snapshot.source_epoch != plan.source_epoch:
        reason = "source_epoch_changed"
    if reason:
        return UndoPreview(plan.operation_id, plan.fingerprint, (), (DryRunConflict(plan.operation_id, reason),))
    if ledger.state == "undone":
        return UndoPreview(plan.operation_id, plan.fingerprint, (), already_undone=True)
    if snapshot.revision != ledger.applied_revision:
        return UndoPreview(
            plan.operation_id, plan.fingerprint, (), (DryRunConflict(plan.operation_id, "snapshot_revision_changed"),)
        )
    revisions = dict(ledger.target_revisions)
    if set(revisions) != {item.id for item in plan.preconditions}:
        return UndoPreview(
            plan.operation_id, plan.fingerprint, (), (DryRunConflict(plan.operation_id, "target_revisions_required"),)
        )
    conflicts = _source_conflicts(plan, snapshot, document, clock, revisions)
    conflicts.extend(_field_conflicts(plan, document))
    return UndoPreview(
        plan.operation_id, plan.fingerprint, () if conflicts else plan.change_set.inverse_ops, tuple(conflicts)
    )


def _source_conflicts(
    plan: DryRunPlan, snapshot: ExportSnapshot, document: dict[str, Any], clock: Clock, revisions: dict[str, int]
) -> list[DryRunConflict]:
    conflicts = []
    for anchor in plan.anchors:
        reason = check_anchor(anchor, snapshot, clock)
        if reason:
            conflicts.append(DryRunConflict(anchor.source_id, reason))
    for guard in plan.preconditions:
        row = document["messages"].get(guard.id)
        reason = "row_missing" if row is None else row_reason(row)
        if row is not None and (
            revisions[guard.id] < guard.revision
            or type(row.get("revision")) is not int
            or row["revision"] != revisions[guard.id]
        ):
            reason = "row_revision_changed"
        if row is not None and digest(immutable_row(row)) != guard.immutable_fingerprint:
            reason = "row_original_changed"
        if reason:
            conflicts.append(DryRunConflict(guard.id, reason))
    return conflicts


def _field_conflicts(plan: DryRunPlan, document: dict[str, Any]) -> list[DryRunConflict]:
    conflicts = []
    for op in plan.change_set.ops:
        collection = document[op.collection]
        if op.field is None:
            current = FieldValue.read(collection, op.entity_id)
            topic_ids = set(op.after.value.get("message_ids", []))
            if any(
                row.get("topic_id") == op.entity_id and identity not in topic_ids
                for identity, row in document["messages"].items()
            ):
                conflicts.append(DryRunConflict(op.entity_id, "later_topic_reference"))
        else:
            row = collection.get(op.entity_id)
            if row is None:
                conflicts.append(DryRunConflict(op.entity_id, "row_missing"))
                continue
            current = FieldValue.read(row, op.field)
        if current != op.after:
            conflicts.append(DryRunConflict(op.entity_id, "label_or_topic_changed"))
    return conflicts

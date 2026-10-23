"""An authenticated owner preview is regenerated from current sources, not a stored display string."""

from dataclasses import asdict

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import digest
from mingjing_core.streaming.json_values import json_object
from mingjing_core.timekit.clock import Clock

from .contracts import DryRunError, DryRunPlan, ExportSnapshot
from .guards import require_snapshot
from .plan_values import plan_fingerprint
from .planner import dry_run_export


def validate_plan(plan: DryRunPlan, scope: MemoryScope) -> None:
    try:
        if not isinstance(plan, DryRunPlan) or plan.scope != scope:
            raise DryRunError("plan_scope_mismatch")
        if plan.fingerprint != plan_fingerprint(plan):
            raise DryRunError("plan_fingerprint_mismatch")
        if plan.input_fingerprint != digest(json_object(plan.original_payload)):
            raise DryRunError("input_fingerprint_mismatch")
    except DryRunError:
        raise
    except (ValueError, TypeError, AttributeError):
        raise DryRunError("plan_invalid") from None


def preview_dry_run(
    plan: DryRunPlan, *, snapshot: ExportSnapshot, scope: MemoryScope, clock: Clock
) -> dict[str, object]:
    require_snapshot(snapshot, scope)
    validate_plan(plan, scope)
    rebuilt = dry_run_export(
        plan.original_payload, snapshot=snapshot, scope=scope, clock=clock, operation_id=plan.operation_id
    )
    if rebuilt.fingerprint != plan.fingerprint:
        raise DryRunError("plan_current_evidence_changed")
    return {
        "dry_run": True,
        "requires_user_review": True,
        "operation_id": plan.operation_id,
        "batch_id": plan.change_set.batch_id,
        "fingerprint": plan.fingerprint,
        "expected_revision": plan.expected_revision,
        "source_epoch": plan.source_epoch,
        "counts": {
            "export_messages": len(plan.original_payload["messages"]),
            "proposed_labels": len(plan.preconditions),
            "topics": len(plan.topics),
            "waiting": len(plan.waiting_ids),
            "conflicts": len(plan.conflicts),
        },
        "topics": [
            {
                "id": item.id,
                "space_id": item.space_id,
                "title": item.title[:80],
                "message_count": len(item.message_ids),
                "start_ms": item.start_ms,
                "end_ms": item.end_ms,
                "sample": item.sample[:80],
            }
            for item in plan.topics
        ],
        "waiting_ids": list(plan.waiting_ids),
        "conflicts": [asdict(item) for item in plan.conflicts],
        "case_migration_strategy": "not_decided_here",
    }

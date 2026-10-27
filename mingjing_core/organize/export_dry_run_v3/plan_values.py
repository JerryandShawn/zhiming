"""Deterministic seals bind label presence, source versions and the original export."""

from dataclasses import asdict

from mingjing_core.organize._change_values import digest

from .contracts import DryRunPlan


def plan_fingerprint(plan: DryRunPlan) -> str:
    return digest(
        {
            "scope": asdict(plan.scope),
            "operation_id": plan.operation_id,
            "export_id": plan.export_id,
            "input_fingerprint": plan.input_fingerprint,
            "expected_revision": plan.expected_revision,
            "source_epoch": plan.source_epoch,
            "change_set": plan.change_set.as_dict(),
            "topics": [{**asdict(item), "message_ids": list(item.message_ids)} for item in plan.topics],
            "waiting_ids": list(plan.waiting_ids),
            "conflicts": [asdict(item) for item in plan.conflicts],
            "preconditions": [asdict(item) for item in plan.preconditions],
            "anchors": [
                [item.source_id, item.revision, item.start, item.end, item.quote_fingerprint] for item in plan.anchors
            ],
        }
    )

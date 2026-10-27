"""Build reversible intentions only; no apply method, I/O adapter or model title generation."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import digest
from mingjing_core.organize.changes import ChangeSet
from mingjing_core.timekit.clock import Clock

from .classification import classify_export
from .codec import parse_export
from .contracts import DryRunConflict, DryRunError, DryRunPlan, ExportSnapshot, ParsedExport, TopicCandidate, identifier
from .guards import precondition, require_snapshot
from .plan_values import plan_fingerprint


def dry_run_export(
    payload: Mapping[str, Any], *, snapshot: ExportSnapshot, scope: MemoryScope, clock: Clock, operation_id: str
) -> DryRunPlan:
    identifier(operation_id)
    before = require_snapshot(snapshot, scope)
    parsed = parse_export(payload, snapshot=snapshot, scope=scope, clock=clock)
    prior = next((item for item in snapshot.operations if item.operation_id == operation_id), None)
    if prior is not None and (prior.input_fingerprint != parsed.input_fingerprint or prior.state == "undone"):
        raise DryRunError("operation_conflict_or_undone")
    after, topics, waiting, conflicts = _target(before, parsed, scope)
    batch_id = "dryrun_" + digest([scope.owner_id, scope.subject_id, operation_id])[:24]
    change_set = ChangeSet.from_documents(
        before, after, batch_id=batch_id, owner_id=scope.owner_id, subject_id=scope.subject_id
    )
    changed_ids = sorted({item.entity_id for item in change_set.ops if item.collection == "messages"})
    lookup = {message.id: message for message in parsed.messages}
    plan = DryRunPlan(
        scope,
        operation_id,
        parsed.export_id,
        parsed.input_fingerprint,
        snapshot.revision,
        snapshot.source_epoch,
        change_set,
        topics,
        waiting,
        conflicts,
        tuple(precondition(before["messages"][identity]) for identity in changed_ids),
        tuple(lookup[identity].anchor for identity in changed_ids),
        parsed.payload,
        "",
    )
    plan = replace(plan, fingerprint=plan_fingerprint(plan), replayed=prior is not None)
    if prior is not None and prior.plan_fingerprint != plan.fingerprint:
        raise DryRunError("operation_plan_changed")
    return plan


def _target(
    before: dict[str, Any], parsed: ParsedExport, scope: MemoryScope
) -> tuple[dict[str, Any], tuple[TopicCandidate, ...], tuple[str, ...], tuple[DryRunConflict, ...]]:
    after = deepcopy(before)
    topics, predictions, parents, waiting = classify_export(parsed, scope)
    lookup = {message.id: message for message in parsed.messages}
    result, conflicts = [], list(parsed.conflicts)
    for topic in topics:
        ids = sorted(
            [*topic.message_ids, *(identity for identity, parent in parents.items() if parent in topic.message_ids)],
            key=lambda identity: (lookup[identity].at_ms, identity),
        )
        if topic.id in before["topics"]:
            conflicts.extend(DryRunConflict(identity, "topic_id_occupied") for identity in ids)
            continue
        if any(
            before["messages"][identity].get("topic_id") is not None
            or before["messages"][identity].get("route_source") == "user"
            for identity in ids
        ):
            conflicts.extend(DryRunConflict(identity, "existing_route_requires_review") for identity in ids)
            continue
        after["topics"][topic.id] = {
            "id": topic.id,
            "owner_id": scope.owner_id,
            "subject_id": scope.subject_id,
            "title": topic.title[:80],
            "space_id": topic.space_id,
            "message_ids": ids,
            "status": "open",
            "revision": 1,
        }
        for identity in ids:
            predicted = predictions[parents.get(identity, identity)]
            after["messages"][identity].update(
                {
                    "space_id": topic.space_id,
                    "topic_id": topic.id,
                    "space_secondary": predicted.secondary_id,
                    "route_source": "migration",
                    "route_confidence": predicted.confidence,
                }
            )
        sample = "\n".join(lookup[identity].text for identity in topic.message_ids)[:80]
        result.append(
            TopicCandidate(
                topic.id,
                topic.space_id,
                topic.title[:80],
                tuple(ids),
                lookup[ids[0]].at_ms,
                lookup[ids[-1]].at_ms,
                sample,
            )
        )
    return after, tuple(result), waiting, tuple(conflicts)

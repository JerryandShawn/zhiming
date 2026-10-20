"""A message-only compatibility view for the old label ChangeSet, never a datastore apply."""

from copy import deepcopy
from typing import Any

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.organize._change_values import FieldValue
from mingjing_core.organize.changes import ChangeSet

from .contracts import LABEL_FIELDS, EntityRecord, ReviewApproval, SupplementConflict, SupplementSnapshot
from .plan_contracts import SupplementPlan
from .projection import project_plan


def _message_matches(record: dict[str, Any], entity: EntityRecord, snapshot: SupplementSnapshot) -> None:
    if entity.kind != "message" or len(entity.anchors) != 1:
        raise SupplementConflict("mainline_entity_adapter_required")
    anchor = entity.anchors[0]
    source = next((item for item in snapshot.sources if item.id == anchor.source_id), None)
    if source is None or source.id != entity.id:
        raise SupplementConflict("message_source_identity_mismatch")
    if (anchor.start, anchor.end, anchor.quote) != (0, len(source.text), source.text) or entity.text != source.text:
        raise SupplementConflict("complete_message_source_required")
    expected = {
        "id": entity.id,
        "owner_id": entity.scope.owner_id,
        "subject_id": entity.scope.subject_id,
        "content": source.text,
        "role": source.role,
        "at_ms": int(source.at.timestamp() * 1000),
        "revision": entity.revision,
    }
    if any(record.get(key, 1 if key == "revision" else None) != value for key, value in expected.items()):
        raise SupplementConflict("legacy_message_evidence_changed")
    if source.revision != entity.revision:
        raise SupplementConflict("legacy_message_revision_changed")
    if any(FieldValue.read(record, key) != FieldValue.read(dict(entity.labels), key) for key in LABEL_FIELDS):
        raise SupplementConflict("legacy_message_labels_changed")


def to_legacy_changeset(
    snapshot: SupplementSnapshot,
    plan: SupplementPlan,
    document: dict[str, Any],
    *,
    scope: MemoryScope,
    approval: ReviewApproval,
) -> ChangeSet:
    """Only message labels can use the frozen messages/topics adapter; other entities need mainline ports."""
    projected = project_plan(snapshot, plan, scope=scope, approval=approval)
    if not isinstance(document, dict) or (document.get("owner_id"), document.get("subject_id")) != (
        scope.owner_id,
        scope.subject_id,
    ):
        raise SupplementConflict("legacy_document_scope_mismatch")
    if any(op.collection != "entities" for op in plan.ops):
        raise SupplementConflict("mainline_topic_adapter_required")
    target = deepcopy(document)
    for identity in {op.entity_id for op in plan.ops}:
        entity = snapshot.entity(identity)
        record = document.get("messages", {}).get(identity)
        if not isinstance(record, dict):
            raise SupplementConflict("legacy_message_missing")
        _message_matches(record, entity, snapshot)
        desired = projected.entity(identity).labels
        for key in LABEL_FIELDS:
            if key in desired:
                target["messages"][identity][key] = desired[key]
            else:
                target["messages"][identity].pop(key, None)
    return ChangeSet.from_documents(
        document,
        target,
        batch_id=plan.operation_id,
        owner_id=scope.owner_id,
        subject_id=scope.subject_id,
    )

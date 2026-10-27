"""Wrap frozen Q5 predictions in a review tray; abstention never becomes a daily assignment."""

from collections.abc import Mapping
from dataclasses import replace

from mingjing_core.memory2.contracts import MemoryScope
from mingjing_core.memory2.sensitivity import Sensitivity
from mingjing_core.memory2.validation import frozen_tuple, require_text
from mingjing_core.organize._change_values import FieldChange, FieldValue
from mingjing_core.organize.v2.contracts import AREA_IDS, Prediction

from .contracts import EntityRecord, ReviewApproval, SensitiveGrant, SupplementConflict, SupplementSnapshot
from .guards import authorize_entity, digest, entity_sensitivity, evidence_fingerprint, require_approval, require_scope
from .plan_contracts import (
    RecordGuard,
    ReviewEntry,
    ReviewProposal,
    SupplementPlan,
    proposal_fingerprint,
    seal_plan,
)


def build_review_proposal(
    snapshot: SupplementSnapshot,
    predictions: Mapping[str, Prediction],
    *,
    scope: MemoryScope,
    operation_id: str,
) -> ReviewProposal:
    require_scope(snapshot, scope)
    require_text(operation_id)
    if not isinstance(predictions, Mapping) or any(type(key) is not str for key in predictions):
        raise SupplementConflict("predictions_invalid")
    entries = []
    for identity, prediction in sorted(predictions.items()):
        entity = snapshot.entity(identity)
        if entity is None or not isinstance(prediction, Prediction):
            raise SupplementConflict("prediction_entity_mismatch")
        authorize_entity(entity, snapshot, scope)
        sensitivity = entity_sensitivity(entity)
        if sensitivity.secret:
            raise SupplementConflict("secret_entity_forbidden")
        entries.append(
            ReviewEntry(
                entity.id,
                entity.kind,
                entity.revision,
                evidence_fingerprint(entity),
                prediction,
                entity.text[:80],
                sensitivity.categories,
                sensitivity.secret,
                sensitivity.profile_confirmation,
                digest(dict(entity.labels)),
            )
        )
    proposal = ReviewProposal(scope, operation_id, snapshot.revision, snapshot.source_epoch, tuple(entries))
    return replace(proposal, fingerprint=proposal_fingerprint(proposal))


def require_proposal(snapshot: SupplementSnapshot, proposal: ReviewProposal, scope: MemoryScope) -> None:
    require_scope(snapshot, scope)
    if not isinstance(proposal, ReviewProposal) or proposal.scope != scope:
        raise SupplementConflict("proposal_scope_mismatch")
    if proposal.fingerprint != proposal_fingerprint(proposal):
        raise SupplementConflict("proposal_fingerprint_mismatch")
    if (snapshot.revision, snapshot.source_epoch) != (proposal.expected_revision, proposal.source_epoch):
        raise SupplementConflict("proposal_snapshot_changed")
    rebuilt = build_review_proposal(
        snapshot,
        {entry.entity_id: entry.prediction for entry in proposal.entries},
        scope=scope,
        operation_id=proposal.operation_id,
    )
    if rebuilt != proposal:
        raise SupplementConflict("proposal_evidence_changed")


def require_sensitive_grant(
    entity: EntityRecord,
    sensitivity: Sensitivity,
    grants: tuple[SensitiveGrant, ...],
    scope: MemoryScope,
) -> None:
    if sensitivity.secret:
        raise SupplementConflict("secret_entity_forbidden")
    if sensitivity.profile_confirmation:
        raise SupplementConflict("birth_profile_confirmation_required")
    if not sensitivity.categories:
        return
    matches = tuple(grant for grant in grants if grant.entity_id == entity.id)
    if len(matches) != 1:
        raise SupplementConflict("sensitive_confirmation_required")
    grant = matches[0]
    if (
        grant.scope != scope
        or grant.entity_revision != entity.revision
        or grant.evidence_fingerprint != evidence_fingerprint(entity)
        or grant.decision != "granted"
        or not set(sensitivity.categories) <= set(grant.categories)
    ):
        raise SupplementConflict("sensitive_confirmation_mismatch")


def _label_ops(entity: EntityRecord, entry: ReviewEntry) -> tuple[FieldChange, ...]:
    desired = dict(entity.labels)
    prediction = entry.prediction
    if desired.get("space_id") != prediction.area_id and desired.get("topic_id") is not None:
        desired["topic_id"] = None
    desired.update(
        {
            "space_id": prediction.area_id,
            "space_secondary": prediction.secondary_id,
            "route_source": "user",
            "route_confidence": prediction.confidence,
        }
    )
    return tuple(
        FieldChange(
            "entities", entity.id, key, FieldValue.read(dict(entity.labels), key), FieldValue.read(desired, key)
        )
        for key in sorted(set(entity.labels) | set(desired))
        if FieldValue.read(dict(entity.labels), key) != FieldValue.read(desired, key)
    )


def plan_review_labels(
    snapshot: SupplementSnapshot,
    proposal: ReviewProposal,
    *,
    scope: MemoryScope,
    approval: ReviewApproval,
    sensitive_grants: tuple[SensitiveGrant, ...] = (),
) -> SupplementPlan:
    require_proposal(snapshot, proposal, scope)
    require_approval(approval, scope, proposal.fingerprint)
    grants = frozen_tuple(sensitive_grants, SensitiveGrant)
    changes, guards = [], []
    for entry in proposal.entries:
        entity = snapshot.entity(entry.entity_id)
        guards.append(RecordGuard("entities", entity.id, entity.revision, evidence_fingerprint(entity)))
        if entry.prediction.waiting:
            continue
        require_sensitive_grant(entity, entity_sensitivity(entity), grants, scope)
        changes.extend(_label_ops(entity, entry))
    return seal_plan(
        SupplementPlan(
            scope,
            proposal.operation_id,
            snapshot.revision,
            snapshot.source_epoch,
            proposal.fingerprint,
            tuple(changes),
            tuple(guards),
            grants,
            reviewed=proposal,
        )
    )


def review_data(proposal: ReviewProposal, snapshot: SupplementSnapshot, *, scope: MemoryScope) -> dict[str, object]:
    require_proposal(snapshot, proposal, scope)

    def item(entry: ReviewEntry) -> dict[str, object]:
        return {
            "entity_id": entry.entity_id,
            "kind": entry.kind,
            "sample": entry.sample,
            "confidence": entry.prediction.confidence,
            "sensitive_confirmation": bool(entry.sensitive_categories),
            "profile_confirmation": entry.profile_confirmation,
            "secret_forbidden": entry.secret,
        }

    return {
        "fingerprint": proposal.fingerprint,
        "areas": [
            {"space_id": area, "items": [item(entry) for entry in proposal.entries if entry.prediction.area_id == area]}
            for area in sorted(AREA_IDS)
        ],
        "waiting": [item(entry) for entry in proposal.waiting],
    }

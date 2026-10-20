"""Current host snapshots are mandatory inputs; these checks do not authenticate PostgreSQL."""

from collections.abc import Mapping, Sequence
from typing import Any

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.application.followups_contracts import FollowupScope
from mingjing_core.scheduling.brief_schedule import BriefSubscription

from .contracts import BasisRef, BriefSourceState


def subscription_basis(subscription: BriefSubscription) -> BasisRef:
    value = {
        "enabled": subscription.enabled,
        "time": subscription.local_time.isoformat(),
        "timezone": subscription.time_zone,
        "revision": subscription.revision,
    }
    return BasisRef(
        "s1",
        "brief-subscription",
        subscription.revision,
        subscription.scope.owner_id,
        subscription.scope.subject_id,
        fingerprint(value),
    )


def state_reason(basis: Sequence[BasisRef], states: Sequence[BriefSourceState], scope: FollowupScope) -> str | None:
    if any((ref.owner_id, ref.subject_id) != (scope.owner_id, scope.subject_id) for ref in basis):
        return "source_scope_mismatch"
    if not states or any(not isinstance(state, BriefSourceState) for state in states):
        return "current_source_state_required"
    supplied = {state.source_id: state for state in states}
    expected = {ref.source_id for ref in basis}
    if len(supplied) != len(states) or set(supplied) != expected:
        return "current_source_manifest_mismatch"
    for ref in basis:
        state = supplied[ref.source_id]
        if state.scope != scope:
            return "source_scope_mismatch"
        if state.revoked:
            return "source_revoked"
        if state.incognito:
            return "source_incognito"
        if not state.active:
            return "source_inactive"
        if state.revision != ref.revision or state.value_sha256 != ref.value_sha256:
            return "source_revision_or_content_changed"
    return None


def transit_state_reason(
    payload: Mapping[str, Any], state: BriefSourceState | None, scope: FollowupScope, profile_revision: int | None
) -> str | None:
    if not isinstance(payload, dict) and not hasattr(payload, "keys"):
        return "transit_payload_required"
    if type(profile_revision) is not int or profile_revision < 0:
        return "current_profile_revision_required"
    document_id = payload.get("document_id")
    if type(document_id) is not str or not document_id.startswith("tool-"):
        return "transit_document_required"
    try:
        basis = BasisRef("c1", document_id, profile_revision, scope.owner_id, scope.subject_id, document_id[5:])
    except ValueError:
        return "transit_document_required"
    return state_reason((basis,), (state,) if state is not None else (), scope)

"""Reject contradictory current host projections before rendering; this is not PG authentication."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from mingjing_core.application.followups_contracts import FollowupScope

from .contracts import BriefingError, BriefItem, BriefSourceState
from .evidence import validate_transit


def validate_current_batch(
    items: Sequence[BriefItem],
    *,
    scope: FollowupScope,
    day: date,
    subscription_state: BriefSourceState | None,
    transit: Mapping[str, Any] | None,
    transit_state: BriefSourceState | None,
    profile_revision: int | None,
) -> None:
    if not isinstance(items, (tuple, list)) or any(not isinstance(item, BriefItem) for item in items):
        raise BriefingError("brief_items_required")
    states = [subscription_state] if isinstance(subscription_state, BriefSourceState) else []
    states.extend(state for item in items for state in item.source_states)
    bound = _bound_transit(transit, transit_state, scope, day, profile_revision)
    if bound is not None:
        states.append(bound)
    by_source: dict[str, BriefSourceState] = {}
    for state in states:
        previous = by_source.get(state.source_id)
        if previous is not None and previous != state:
            raise BriefingError("brief_current_source_manifest_inconsistent")
        by_source[state.source_id] = state


def _bound_transit(
    payload: Mapping[str, Any] | None,
    state: BriefSourceState | None,
    scope: FollowupScope,
    day: date,
    revision: int | None,
) -> BriefSourceState | None:
    if not isinstance(payload, Mapping) or not isinstance(state, BriefSourceState) or type(revision) is not int:
        return None
    try:
        snapshot = validate_transit(payload, scope=scope, day=day, profile_revision=revision)
    except (ValueError, TypeError, KeyError):
        return None
    document = snapshot.payload["document_id"]
    if (state.source_id, state.scope, state.revision, state.value_sha256) != (document, scope, revision, document[5:]):
        return None
    # Revoked/inactive/incognito states remain in the manifest so a second active projection cannot overrule them.
    return state

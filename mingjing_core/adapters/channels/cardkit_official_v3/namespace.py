"""A new namespace child; legacy stream/checkpoint proof is preserved and never silently upgraded."""

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from mingjing_core.adapters.channels.cardkit_checkpoint import restore_snapshot
from mingjing_core.adapters.channels.cardkit_contracts import CardScope, canonical, fingerprint
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import ReconciliationBinding, namespace_fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamScope
from mingjing_core.adapters.channels.stream_outbox_v2 import restore_state as restore_lease

from .codec import restore_state, state_metadata
from .contracts import OfficialError, OfficialState


@dataclass(frozen=True)
class OfficialMerge:
    expected_row_revision: int
    next_row_revision: int
    expected_namespace_fingerprint: str
    namespace_fingerprint: str
    changed: bool
    _json: str = field(repr=False)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._json)


def merge_official_reconciliation(
    reconciliation: Mapping[str, Any],
    *,
    binding: ReconciliationBinding,
    current_row_revision: int,
    expected_row_revision: int,
    expected_namespace_fingerprint: str,
    state: OfficialState,
) -> OfficialMerge:
    if type(current_row_revision) is not int or current_row_revision < 0 or type(expected_row_revision) is not int:
        raise OfficialError("namespace_revision_invalid")
    if (
        current_row_revision != expected_row_revision
        or namespace_fingerprint(reconciliation) != expected_namespace_fingerprint
    ):
        raise OfficialError("namespace_cas_conflict")
    if (
        not isinstance(binding, ReconciliationBinding)
        or not isinstance(state, OfficialState)
        or asdict(state.scope) != asdict(binding)
    ):
        raise OfficialError("namespace_binding_mismatch")
    raw = json.loads(canonical(dict(reconciliation)))
    old = raw.get("cardkit", {"schema": "cardkit.outbox.namespace.v2", "binding": asdict(binding), "revision": 0})
    if (
        not isinstance(old, dict)
        or old.get("schema") != "cardkit.outbox.namespace.v2"
        or old.get("binding") != asdict(binding)
    ):
        raise OfficialError("legacy_namespace_requires_explicit_migration")
    if type(old.get("revision")) is not int or old["revision"] < 0:
        raise OfficialError("namespace_revision_invalid")
    _legacy_binding(old, state)
    data = state_metadata(state)
    if "official_v3" in old:
        prior = restore_state(old["official_v3"], scope=StreamScope(**asdict(binding)))
        if old["official_v3"] != data:
            _monotonic(prior, state, old["official_v3"], data)
    changed = old.get("official_v3") != data
    updated = {**old, "official_v3": data, "revision": old["revision"] + int(changed)}
    raw["cardkit"] = updated
    return OfficialMerge(
        current_row_revision,
        current_row_revision + int(changed),
        expected_namespace_fingerprint,
        fingerprint(updated),
        changed,
        canonical(raw),
    )


def _legacy_binding(namespace: dict, state: OfficialState) -> None:
    for legacy in _legacy_states(namespace, state):
        if not isinstance(legacy, dict):
            raise OfficialError("legacy_state_invalid")
        if legacy.get("phase") in {"dispatched", "uncertain", "in_flight"} or legacy.get("pending") is not None:
            raise OfficialError("legacy_unknown_requires_reconciliation")
        for key in ("card_id", "message_id"):
            if legacy.get(key) is not None and legacy[key] != getattr(state, key):
                raise OfficialError("legacy_remote_identity_changed")
        if legacy.get("last_reserved_sequence", 0) > state.last_reserved_sequence:
            raise OfficialError("legacy_sequence_regressed")
        if legacy.get("last_acked_sequence", 0) > state.last_acked_sequence:
            raise OfficialError("legacy_ack_sequence_regressed")
        if legacy.get("fence", 0) > (state.lease_state.fence if state.lease_state is not None else 0):
            raise OfficialError("legacy_fence_regressed")
        if legacy.get("phase") == "closed" and not state.close_acked:
            raise OfficialError("legacy_closed_requires_explicit_migration")


def _legacy_states(namespace: dict, state: OfficialState) -> list[dict]:
    rows = []
    if "stream" in namespace:
        restore_lease(namespace["stream"], scope=state.scope)
        rows.append(namespace["stream"])
    if "checkpoint" in namespace:
        scope = state.scope
        restore_snapshot(
            namespace["checkpoint"], scope=CardScope(scope.owner_id, scope.subject_id, scope.target, scope.business_id)
        )
        rows.append(namespace["checkpoint"]["checkpoint"])
    return rows


def _monotonic(prior: OfficialState, state: OfficialState, old: dict, data: dict) -> None:
    for key in ("revision", "last_reserved_sequence", "last_acked_sequence", "close_retries"):
        if getattr(state, key) < getattr(prior, key):
            raise OfficialError("official_namespace_regressed")
    if old != data and state.revision <= old["revision"]:
        raise OfficialError("official_namespace_revision_reused")
    for key in ("card_id", "message_id"):
        if getattr(prior, key) is not None and getattr(state, key) != getattr(prior, key):
            raise OfficialError("official_remote_identity_changed")
    if prior.phase in {"dispatched", "uncertain"} and (
        state.lease_state is None or state.lease_state.phase in {"prepared", "leased"}
    ):
        raise OfficialError("official_unknown_cannot_retry")
    if prior.phase in {"dispatched", "uncertain"}:
        _unknown_settlement(prior, state)
    if prior.lease_state is not None and (
        state.lease_state is None or state.lease_state.fence < prior.lease_state.fence
    ):
        raise OfficialError("official_fence_regressed")
    if prior.close_acked and not state.close_acked:
        raise OfficialError("closed_state_regressed")


def _unknown_settlement(prior: OfficialState, state: OfficialState) -> None:
    if (
        prior.operation != state.operation
        or prior.lease_state.dispatch_fingerprint != state.lease_state.dispatch_fingerprint
    ):
        raise OfficialError("official_unknown_operation_changed")
    if state.lease_state.phase in {"acked", "rejected"} and state.lease_state.evidence_ref is None:
        raise OfficialError("official_unknown_requires_settlement_evidence")

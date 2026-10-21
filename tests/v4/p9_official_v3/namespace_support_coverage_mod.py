"""Synthetic namespace migration fixtures, with no persistence or remote authority."""

from dataclasses import asdict

from mingjing_core.adapters.channels.cardkit_checkpoint import snapshot
from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope, fingerprint
from mingjing_core.adapters.channels.cardkit_official_v3 import OfficialState, merge_official_reconciliation
from mingjing_core.adapters.channels.cardkit_reconciliation_v2 import ReconciliationBinding, namespace_fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import state_metadata as lease_metadata

from .support_mod import Environment


def binding(env: Environment) -> ReconciliationBinding:
    return ReconciliationBinding(**asdict(env.scope))


def old_checkpoint(state: OfficialState, phase: str = "streaming") -> CardCheckpoint:
    scope = state.scope
    return CardCheckpoint(
        CardScope(scope.owner_id, scope.subject_id, scope.target, scope.business_id),
        phase=phase,
        version=3,
        card_id=state.card_id,
        message_id=state.message_id,
        last_reserved_sequence=state.last_reserved_sequence,
        last_acked_sequence=state.last_acked_sequence,
        initial_fingerprint=fingerprint({"synthetic": "original-approved-card"}),
        final_fingerprint=fingerprint({"synthetic": "final-approved-card"}) if phase == "closed" else None,
    )


def legacy_container(env: Environment, state: OfficialState, mode: str = "both") -> dict:
    namespace = {
        "schema": "cardkit.outbox.namespace.v2",
        "binding": asdict(binding(env)),
        "revision": 3,
        "unknown_vendor_child": {"proof_id": "synthetic-vendor-proof", "flags": [1, 2]},
    }
    if mode in {"stream", "both"}:
        namespace["stream"] = lease_metadata(state.lease_state)
    if mode in {"checkpoint", "both"}:
        namespace["checkpoint"] = snapshot(old_checkpoint(state))
    return {"old_delivery_proof": {"source_revision": 7, "accepted": True}, "cardkit": namespace}


def merge(
    value: dict,
    state: OfficialState,
    env: Environment,
    *,
    row: int = 7,
    expected_row: int | None = None,
    expected_fp: str | None = None,
) -> object:
    return merge_official_reconciliation(
        value,
        binding=binding(env),
        current_row_revision=row,
        expected_row_revision=row if expected_row is None else expected_row,
        expected_namespace_fingerprint=namespace_fingerprint(value) if expected_fp is None else expected_fp,
        state=state,
    )

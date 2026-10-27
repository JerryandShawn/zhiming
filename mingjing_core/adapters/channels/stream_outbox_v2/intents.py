"""Preparing metadata is not permission to perform an external side effect."""

from dataclasses import replace

from mingjing_core.adapters.channels.cardkit_checkpoint import restore_snapshot, snapshot
from mingjing_core.adapters.channels.cardkit_contracts import CardCheckpoint, CardScope, fingerprint

from .contracts import IntentRecord, StreamError, StreamIntent, StreamScope, StreamState
from .guards import cas


def prepare_intent(
    scope: StreamScope,
    *,
    operation_id: str,
    kind: str,
    payload_fingerprint: str,
    checkpoint: CardCheckpoint | None = None,
    sequence: int | None = None,
) -> StreamState:
    if not isinstance(scope, StreamScope):
        raise StreamError("intent_scope_invalid")
    if type(kind) is not str:
        raise StreamError("operation_kind_invalid")
    card_id, message_id, reserved, acked = None, None, 0, 0
    if checkpoint is not None:
        if not isinstance(checkpoint, CardCheckpoint):
            raise StreamError("checkpoint_invalid")
        card_scope = CardScope(scope.owner_id, scope.subject_id, scope.target, scope.business_id)
        if scope.channel != "feishu" or checkpoint.scope != card_scope:
            raise StreamError("checkpoint_scope_mismatch")
        try:
            checkpoint = restore_snapshot(snapshot(checkpoint), scope=card_scope)
        except ValueError:
            raise StreamError("checkpoint_invalid") from None
        if checkpoint.pending is not None or checkpoint.phase in {
            "uncertain",
            "in_flight",
            "closed",
            "fallback_pending",
        }:
            raise StreamError("checkpoint_not_resumable")
        card_id, message_id = checkpoint.card_id, checkpoint.message_id
        reserved, acked = checkpoint.last_reserved_sequence, checkpoint.last_acked_sequence
    sequence = _sequence(kind, sequence, reserved)
    _stage(kind, card_id, message_id)
    intent = StreamIntent(operation_id, kind, payload_fingerprint, sequence)
    return StreamState(
        scope,
        intent,
        card_id=card_id,
        message_id=message_id,
        last_reserved_sequence=sequence or reserved,
        last_acked_sequence=acked,
    )


def _sequence(kind: str, sequence: int | None, reserved: int) -> int | None:
    if kind in {"update", "close"}:
        if sequence is not None and (type(sequence) is not int or sequence != reserved + 1):
            raise StreamError("sequence_must_increase")
        return reserved + 1
    if sequence is not None:
        raise StreamError("unexpected_sequence")
    return None


def _stage(kind: str, card_id: str | None, message_id: str | None) -> None:
    expected = "create" if card_id is None else "send" if message_id is None else "streaming"
    if (expected == "streaming" and kind not in {"update", "close"}) or (expected != "streaming" and kind != expected):
        raise StreamError("operation_stage_invalid")


def next_intent(
    state: StreamState,
    *,
    operation_id: str,
    kind: str,
    payload_fingerprint: str,
    expected_revision: int,
    sequence: int | None = None,
) -> StreamState:
    cas(state, expected_revision)
    if state.phase not in {"acked", "rejected"} or (state.phase == "acked" and state.intent.kind == "close"):
        raise StreamError("previous_intent_not_settled")
    prior = next(
        (
            item
            for item in (*state.history, IntentRecord(state.intent, state.phase))
            if item.intent.operation_id == operation_id
        ),
        None,
    )
    if prior is not None:
        if prior.intent.kind != kind or prior.intent.payload_fingerprint != payload_fingerprint:
            raise StreamError("operation_payload_changed")
        return state
    if state.phase == "rejected" and (
        kind != state.intent.kind or payload_fingerprint != state.intent.payload_fingerprint
    ):
        raise StreamError("rejected_intent_payload_changed")
    _stage(kind, state.card_id, state.message_id)
    sequence = _sequence(kind, sequence, state.last_reserved_sequence)
    intent = StreamIntent(operation_id, kind, payload_fingerprint, sequence)
    return replace(
        state,
        intent=intent,
        phase="prepared",
        revision=state.revision + 1,
        lease=None,
        history=(*state.history, IntentRecord(state.intent, state.phase)),
        evidence_ref=None,
        dispatch_fingerprint=None,
        last_reserved_sequence=sequence or state.last_reserved_sequence,
        attempts=state.attempts if state.phase == "rejected" else 0,
    )


def fallback_intent(state: StreamState) -> StreamIntent | None:
    if state.phase != "rejected" or state.intent.kind != "close" or state.evidence_ref is None:
        return None
    operation = "stream-fallback:" + fingerprint(
        [state.scope.outbox_id, state.intent.operation_id, state.intent.payload_fingerprint]
    )
    return StreamIntent(operation, "fallback", state.intent.payload_fingerprint)

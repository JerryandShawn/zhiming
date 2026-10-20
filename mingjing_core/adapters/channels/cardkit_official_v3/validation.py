"""Fail closed on malformed metadata; IDs and sequence limits are shared with new builders."""

from mingjing_core.adapters.channels.card_limits_official_v3 import validate_card_id, validate_sequence
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamScope, StreamState
from mingjing_core.adapters.channels.stream_outbox_v2.contracts import digest, identity, integer, utc

from .contracts import OfficialError, OfficialOperation, OfficialPolicy, OfficialState


def validate_state(state: OfficialState) -> None:
    if not isinstance(state.scope, StreamScope) or not isinstance(state.policy, OfficialPolicy):
        raise OfficialError("state_scope_or_policy_invalid")
    if type(state.stage) is not str or state.stage not in {
        "new",
        "created",
        "streaming",
        "finalized",
        "closed",
        "fallback_pending",
        "streaming_close_failed",
        "needs_host_decision",
    }:
        raise OfficialError("stage_invalid")
    for key in ("revision", "last_reserved_sequence", "last_acked_sequence", "close_retries"):
        integer(getattr(state, key))
    if state.close_retries > 1 or state.last_acked_sequence > state.last_reserved_sequence:
        raise OfficialError("counter_order_invalid")
    if state.last_reserved_sequence:
        validate_sequence(state.last_reserved_sequence)
    if any(type(getattr(state, key)) is not bool for key in ("finalize_acked", "close_acked")):
        raise OfficialError("ack_flags_invalid")
    if state.close_acked and not state.finalize_acked:
        raise OfficialError("close_before_finalize")
    if (state.stage == "closed") != state.close_acked:
        raise OfficialError("closed_requires_both_acks")
    for key in ("last_attempt_at", "started_at", "not_before"):
        value = getattr(state, key)
        if value is not None:
            object.__setattr__(state, key, utc(value))
    if state.card_id is not None:
        validate_card_id(state.card_id)
    if state.message_id is not None:
        identity(state.message_id)
    if state.message_id is not None and state.card_id is None:
        raise OfficialError("message_without_card")
    if not isinstance(state.history, (tuple, list)) or any(not isinstance(x, OfficialOperation) for x in state.history):
        raise OfficialError("history_invalid")
    object.__setattr__(state, "history", tuple(state.history))
    operations = [x.operation_id for x in state.history]
    if len(set(operations)) != len(operations):
        raise OfficialError("history_duplicate")
    _validate_operation(state, operations)
    _validate_stage(state)


def _validate_operation(state: OfficialState, operations: list[str]) -> None:
    inner, operation = state.lease_state, state.operation
    if (inner is None) != (operation is None):
        raise OfficialError("operation_lease_missing")
    if inner is None:
        if state.artifact_fingerprint is not None or operations or state.revision or state.last_reserved_sequence:
            raise OfficialError("initial_state_has_operation_metadata")
        if any(
            getattr(state, key) is not None for key in ("retry_kind", "retry_reason", "last_attempt_at", "not_before")
        ):
            raise OfficialError("initial_state_has_retry_metadata")
        return
    if not isinstance(inner, StreamState) or not isinstance(operation, OfficialOperation) or inner.scope != state.scope:
        raise OfficialError("operation_scope_invalid")
    if operation.operation_id in operations:
        raise OfficialError("operation_in_history")
    expected_kind = operation.kind if operation.kind in {"create", "send"} else "update"
    if inner.intent.kind != expected_kind:
        raise OfficialError("operation_wire_kind_mismatch")
    if (inner.intent.operation_id, inner.intent.payload_fingerprint, inner.intent.sequence) != (
        operation.operation_id,
        operation.payload_fingerprint,
        operation.sequence,
    ):
        raise OfficialError("operation_lease_mismatch")
    if inner.card_id != state.card_id or inner.message_id != state.message_id:
        raise OfficialError("operation_remote_mismatch")
    if (
        inner.last_reserved_sequence != state.last_reserved_sequence
        or inner.last_acked_sequence != state.last_acked_sequence
    ):
        raise OfficialError("operation_sequence_mismatch")
    if operation.sequence is not None:
        validate_sequence(operation.sequence)
    digest(state.artifact_fingerprint)
    sequences = [row.sequence for row in (*state.history, operation) if row.sequence is not None]
    if sequences != sorted(sequences) or (sequences and sequences[-1] != state.last_reserved_sequence):
        raise OfficialError("history_sequence_invalid")


def _validate_stage(state: OfficialState) -> None:
    inner, operation = state.lease_state, state.operation
    known_card = state.stage != "new"
    known_message = state.stage not in {"new", "created"}
    if known_card != (state.card_id is not None) or known_message != (state.message_id is not None):
        raise OfficialError("stage_remote_identity_invalid")
    if known_message != (state.started_at is not None):
        raise OfficialError("stage_start_time_invalid")
    if inner is None:
        if state.stage != "new" or state.finalize_acked or state.close_acked or state.close_retries:
            raise OfficialError("stage_operation_required")
        return
    if state.retry_kind is not None and (
        state.retry_kind != operation.kind or inner.phase != "rejected" or state.retry_reason is None
    ):
        raise OfficialError("retry_state_invalid")
    if state.retry_reason is not None:
        identity(state.retry_reason)
    if state.stage in {"finalized", "closed", "streaming_close_failed"} and not state.finalize_acked:
        raise OfficialError("finalize_ack_required")
    if state.stage in {"new", "created", "streaming"} and state.finalize_acked:
        raise OfficialError("unexpected_finalize_ack")
    if state.stage == "closed" and (operation.kind != "close_streaming" or inner.phase != "acked"):
        raise OfficialError("close_ack_operation_required")
    if state.stage == "fallback_pending" and (
        operation.kind != "finalize" or inner.phase != "rejected" or inner.evidence_ref is None
    ):
        raise OfficialError("fallback_requires_verified_finalize_refusal")
    if state.stage == "streaming_close_failed" and (
        operation.kind != "close_streaming" or inner.phase != "rejected" or state.close_retries != 1
    ):
        raise OfficialError("close_failure_state_invalid")
    stages = {
        "create": {"new", "created"},
        "send": {"created", "streaming"},
        "update": {"streaming", "needs_host_decision"},
        "finalize": {"streaming", "finalized", "fallback_pending", "needs_host_decision"},
        "close_streaming": {"finalized", "closed", "streaming_close_failed", "needs_host_decision"},
    }
    if state.stage not in stages[operation.kind]:
        raise OfficialError("stage_operation_mismatch")
    _stage_settlement(state)


def _stage_settlement(state: OfficialState) -> None:
    kind, phase = state.operation.kind, state.lease_state.phase
    if phase == "acked":
        expected = {
            "create": "created",
            "send": "streaming",
            "update": "streaming",
            "finalize": "finalized",
            "close_streaming": "closed",
        }[kind]
        if state.stage != expected:
            raise OfficialError("acked_operation_stage_invalid")
    elif phase in {"prepared", "leased", "dispatched", "uncertain"}:
        expected = {
            "create": {"new"},
            "send": {"created"},
            "update": {"streaming"},
            "finalize": {"streaming", "needs_host_decision"},
            "close_streaming": {"finalized"},
        }[kind]
        if state.stage not in expected:
            raise OfficialError("unconfirmed_operation_stage_invalid")
    if state.finalize_acked and not (
        (kind == "finalize" and phase == "acked") or any(row.kind == "finalize" for row in state.history)
    ):
        raise OfficialError("finalize_history_missing")

"""Prepare descriptions, never I/O. Unknown operations cannot be replaced or retried."""

from dataclasses import replace
from datetime import timedelta
from typing import Any

from mingjing_core.adapters.channels.card_limits_official_v3 import validate_sequence
from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.adapters.channels.stream_outbox_v2 import StreamIntent, StreamScope, StreamState
from mingjing_core.timekit.clock import Clock

from .contracts import (
    ArtifactEvidence,
    OfficialError,
    OfficialFallback,
    OfficialOperation,
    OfficialPolicy,
    OfficialState,
    PreparedOperation,
    now_utc,
)
from .wire import build_wire_request


def new_state(scope: StreamScope, policy: OfficialPolicy | None = None) -> OfficialState:
    if not isinstance(scope, StreamScope) or scope.channel != "feishu":
        raise OfficialError("feishu_scope_required")
    return OfficialState(scope, policy or OfficialPolicy())


def prepare_operation(
    state: OfficialState,
    kind: str,
    payload: Any = None,
    *,
    operation_id: str,
    artifact: ArtifactEvidence,
    clock: Clock,
) -> PreparedOperation:
    if (
        not isinstance(state, OfficialState)
        or not isinstance(artifact, ArtifactEvidence)
        or artifact.scope != state.scope
    ):
        raise OfficialError("prepare_scope_invalid")
    now = now_utc(clock.now())
    if kind == "update" and payload == "":
        return PreparedOperation(state, status="noop_empty")
    replayed = _replay(state, kind, payload, operation_id, artifact)
    if replayed is not None:
        return replayed
    _allowed(state, kind, now)
    sequenced = kind in {"update", "finalize", "close_streaming"}
    sequence = validate_sequence(state.last_reserved_sequence + 1) if sequenced else None
    request = build_wire_request(state, kind, payload, operation_id=operation_id, sequence=sequence, artifact=artifact)
    if sequenced and _reuse(state, request.content_fingerprint):
        sequence = state.last_reserved_sequence
        request = build_wire_request(
            state, kind, payload, operation_id=operation_id, sequence=sequence, artifact=artifact
        )
    operation = OfficialOperation(
        kind, operation_id, request.wire_uuid, request.fingerprint, sequence, request.content_fingerprint
    )
    inner = _inner(state, operation)
    history = (*state.history, state.operation) if state.operation else state.history
    prepared = replace(
        state,
        revision=state.revision + 1,
        operation=operation,
        lease_state=inner,
        history=history,
        artifact_fingerprint=artifact.fingerprint,
        last_reserved_sequence=sequence or state.last_reserved_sequence,
        retry_kind=None,
        retry_reason=None,
        not_before=None,
        close_retries=state.close_retries + int(kind == "close_streaming" and state.retry_reason == "close_rejected"),
    )
    return PreparedOperation(prepared, request)


def _replay(
    state: OfficialState,
    kind: str,
    payload: Any,
    operation_id: str,
    artifact: ArtifactEvidence,
) -> PreparedOperation | None:
    prior = next(
        (
            row
            for row in (*state.history, *((state.operation,) if state.operation else ()))
            if row.operation_id == operation_id
        ),
        None,
    )
    if prior is None:
        return None
    request = build_wire_request(
        state, kind, payload, operation_id=operation_id, sequence=prior.sequence, artifact=artifact
    )
    if prior.content_fingerprint != request.content_fingerprint or prior.kind != kind:
        raise OfficialError("operation_payload_changed")
    return PreparedOperation(state, status="replayed")


def _allowed(state: OfficialState, kind: str, now: Any) -> None:
    if state.lease_state is not None and state.lease_state.phase not in {"acked", "rejected"}:
        raise OfficialError("previous_operation_not_settled")
    allowed = {
        "new": {"create"},
        "created": {"send"},
        "streaming": {"update", "finalize"},
        "finalized": {"close_streaming"},
        "needs_host_decision": {"finalize"},
    }
    if kind not in allowed.get(state.stage, set()):
        raise OfficialError("operation_stage_invalid")
    if state.not_before is not None and now < state.not_before:
        raise OfficialError("retry_not_due")
    if state.last_attempt_at is not None:
        if now < state.last_attempt_at:
            raise OfficialError("clock_went_backwards")
        if kind in {"update", "finalize", "close_streaming"} and now - state.last_attempt_at < timedelta(
            milliseconds=state.policy.interval_ms
        ):
            raise OfficialError("cardkit_throttled")


def _reuse(state: OfficialState, content_fingerprint: str) -> bool:
    return (
        not state.policy.allow_sequence_gaps
        and state.retry_kind is not None
        and state.retry_reason not in {"cardkit_200810", "cardkit_300317", "close_rejected"}
        and state.operation is not None
        and state.operation.sequence is not None
        and state.operation.content_fingerprint == content_fingerprint
        and state.lease_state.phase == "rejected"
    )


def _inner(state: OfficialState, operation: OfficialOperation) -> StreamState:
    kind = operation.kind if operation.kind in {"create", "send"} else "update"
    prior = state.lease_state
    return StreamState(
        state.scope,
        StreamIntent(operation.operation_id, kind, operation.payload_fingerprint, operation.sequence),
        revision=prior.revision + 1 if prior else 0,
        fence=prior.fence if prior else 0,
        card_id=state.card_id,
        message_id=state.message_id,
        last_reserved_sequence=operation.sequence or state.last_reserved_sequence,
        last_acked_sequence=state.last_acked_sequence,
    )


def stream_deadline_action(state: OfficialState, *, clock: Clock) -> str | None:
    # 已核实（26转录）：https://open.feishu.cn/document/cardkit-v1/streaming-updates-openapi-overview (2025-06-27).
    if (
        state.started_at is not None
        and not state.close_acked
        and now_utc(clock.now()) >= state.started_at + timedelta(minutes=10)
    ):
        return "reopen_or_finalize"
    return None


def fallback_intent(state: OfficialState) -> OfficialFallback | None:
    """A metadata-only intent; host must recheck freshness before an independent text outbox effect."""
    if not isinstance(state, OfficialState) or state.stage != "fallback_pending":
        return None
    if state.lease_state.phase != "rejected" or state.operation.kind != "finalize":
        return None
    operation = "official-fallback:" + fingerprint(
        [state.scope.outbox_id, state.operation.operation_id, state.artifact_fingerprint]
    )
    return OfficialFallback(operation, state.card_id, state.message_id, state.artifact_fingerprint)

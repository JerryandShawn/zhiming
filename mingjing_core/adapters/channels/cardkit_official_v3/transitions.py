"""The host persists every returned state under CAS before executing any described request."""

from dataclasses import replace
from datetime import timedelta

from mingjing_core.adapters.channels import stream_outbox_v2 as q6
from mingjing_core.timekit.clock import Clock

from .artifacts import validate_artifact
from .contracts import (
    ArtifactEvidence,
    OfficialAck,
    OfficialError,
    OfficialOutcome,
    OfficialRequest,
    OfficialState,
    now_utc,
)


def _cas(state: OfficialState, revision: int) -> None:
    if type(revision) is not int or not isinstance(state, OfficialState) or revision != state.revision:
        raise OfficialError("revision_conflict")
    if state.lease_state is None or state.operation is None:
        raise OfficialError("prepared_operation_required")


def claim(
    state: OfficialState,
    request: OfficialRequest,
    *,
    artifact: ArtifactEvidence,
    evidence: q6.FreshnessEvidence,
    token: str,
    worker_id: str,
    clock: Clock,
    ttl: timedelta,
    expected_revision: int,
) -> OfficialState:
    _cas(state, expected_revision)
    validate_artifact(state, request, artifact, evidence, "claim", now_utc(clock.now()))
    grant = q6.claim(
        state.lease_state,
        token=token,
        worker_id=worker_id,
        clock=clock,
        ttl=ttl,
        evidence=evidence,
        expected_revision=state.lease_state.revision,
    )
    return replace(state, lease_state=grant.state, revision=state.revision + 1)


def begin_dispatch(
    state: OfficialState,
    request: OfficialRequest,
    *,
    artifact: ArtifactEvidence,
    evidence: q6.FreshnessEvidence,
    token: str,
    fence: int,
    clock: Clock,
    expected_revision: int,
) -> OfficialState:
    _cas(state, expected_revision)
    validate_artifact(state, request, artifact, evidence, "dispatch", now_utc(clock.now()))
    inner = q6.begin_dispatch(
        state.lease_state,
        token=token,
        fence=fence,
        clock=clock,
        evidence=evidence,
        expected_revision=state.lease_state.revision,
    )
    return replace(state, lease_state=inner, revision=state.revision + 1, last_attempt_at=now_utc(clock.now()))


def _receipt(state: OfficialState, ack: OfficialAck, evidence_ref: str) -> q6.StreamReceipt:
    if not isinstance(ack, OfficialAck):
        raise OfficialError("ack_required")
    operation = state.operation
    if ack.sequence is not None and (type(ack.sequence) is not int or ack.sequence != operation.sequence):
        raise OfficialError("ack_sequence_mismatch")
    return q6.StreamReceipt(
        state.scope,
        operation.operation_id,
        operation.payload_fingerprint,
        operation.sequence,
        ack.card_id,
        ack.message_id,
        evidence_ref,
    )


def settle_ack(
    state: OfficialState,
    ack: OfficialAck,
    *,
    evidence_ref: str,
    token: str,
    fence: int,
    clock: Clock,
    expected_revision: int,
) -> OfficialState:
    _cas(state, expected_revision)
    receipt = _receipt(state, ack, evidence_ref)
    inner = q6.acknowledge(
        state.lease_state, receipt, token=token, fence=fence, clock=clock, expected_revision=state.lease_state.revision
    )
    return _acked(state, inner, now_utc(clock.now()))


def _acked(state: OfficialState, inner: q6.StreamState, now: object) -> OfficialState:
    kind = state.operation.kind
    stage = {
        "create": "created",
        "send": "streaming",
        "update": "streaming",
        "finalize": "finalized",
        "close_streaming": "closed",
    }[kind]
    return replace(
        state,
        lease_state=inner,
        revision=state.revision + 1,
        stage=stage,
        card_id=inner.card_id,
        message_id=inner.message_id,
        last_acked_sequence=inner.last_acked_sequence,
        finalize_acked=state.finalize_acked or kind == "finalize",
        close_acked=kind == "close_streaming",
        started_at=now if kind == "send" else state.started_at,
        retry_kind=None,
        retry_reason=None,
        not_before=None,
    )


def settle_outcome(
    state: OfficialState,
    outcome: OfficialOutcome,
    *,
    evidence_ref: str,
    token: str,
    fence: int,
    clock: Clock,
    expected_revision: int,
) -> OfficialState:
    _cas(state, expected_revision)
    if not isinstance(outcome, OfficialOutcome):
        raise OfficialError("outcome_required")
    if outcome.status == "uncertain":
        inner = q6.mark_uncertain(
            state.lease_state, token=token, fence=fence, clock=clock, expected_revision=state.lease_state.revision
        )
        return replace(state, lease_state=inner, revision=state.revision + 1)
    ack = OfficialAck(state.card_id, state.message_id, state.operation.sequence)
    inner = q6.reject(
        state.lease_state,
        _receipt(state, ack, evidence_ref),
        token=token,
        fence=fence,
        clock=clock,
        expected_revision=state.lease_state.revision,
    )
    return _refused(state, inner, outcome, clock)


def _refused(state: OfficialState, inner: q6.StreamState, outcome: OfficialOutcome, clock: Clock) -> OfficialState:
    kind, stage, retry = state.operation.kind, state.stage, None
    if outcome.status == "retryable":
        retry = kind
        if outcome.action_required is not None:
            stage, retry = "needs_host_decision", None
    elif kind == "finalize":
        stage = "fallback_pending"
    elif kind == "close_streaming":
        stage = "streaming_close_failed" if state.close_retries else "finalized"
        retry = None if state.close_retries else kind
    return replace(
        state,
        lease_state=inner,
        revision=state.revision + 1,
        stage=stage,
        retry_kind=retry,
        retry_reason="close_rejected" if kind == "close_streaming" and outcome.status == "rejected" else outcome.reason,
        not_before=now_utc(clock.now()) + timedelta(milliseconds=outcome.after_ms),
    )


def recover_expired(state: OfficialState, *, clock: Clock, expected_revision: int) -> OfficialState:
    _cas(state, expected_revision)
    inner = q6.recover_expired(state.lease_state, clock=clock, expected_revision=state.lease_state.revision)
    return replace(state, lease_state=inner, revision=state.revision + 1)


def reconcile(
    state: OfficialState,
    ack: OfficialAck,
    *,
    delivered: bool,
    evidence_ref: str,
    clock: Clock,
    expected_revision: int,
) -> OfficialState:
    _cas(state, expected_revision)
    inner = q6.reconcile(
        state.lease_state,
        _receipt(state, ack, evidence_ref),
        delivered=delivered,
        expected_revision=state.lease_state.revision,
    )
    if delivered:
        return _acked(state, inner, now_utc(clock.now()))
    return _refused(state, inner, OfficialOutcome("rejected", "verified_not_executed"), clock)

"""Persist each returned state using host CAS before invoking a transport; this module does no I/O."""

from dataclasses import replace
from datetime import timedelta

from mingjing_core.adapters.channels.cardkit_contracts import fingerprint
from mingjing_core.timekit.clock import Clock

from .contracts import LeaseGrant, StreamError, StreamLease, StreamReceipt, StreamState, identity, integer, utc
from .freshness import FreshnessEvidence, validate_freshness
from .guards import bound_receipt, cas, live_lease, token_hash


def _duration(ttl: timedelta) -> None:
    if not isinstance(ttl, timedelta) or not timedelta(0) < ttl <= timedelta(minutes=10):
        raise StreamError("lease_duration_invalid")


def claim(
    state: StreamState,
    *,
    token: str,
    worker_id: str,
    clock: Clock,
    ttl: timedelta,
    evidence: FreshnessEvidence,
    expected_revision: int,
    max_attempts: int = 3,
) -> LeaseGrant:
    cas(state, expected_revision)
    now = utc(clock.now())
    identity(worker_id)
    _duration(ttl)
    integer(max_attempts, 1)
    if max_attempts > 10 or state.attempts >= max_attempts:
        raise StreamError("attempt_limit_reached")
    if state.phase == "leased":
        if now < state.lease.expires_at:
            raise StreamError("lease_already_claimed")
    elif state.phase != "prepared":
        raise StreamError("intent_not_claimable")
    validate_freshness(state, evidence, "claim", now)
    lease = StreamLease(token_hash(token), worker_id, state.fence + 1, now + ttl)
    result = replace(state, phase="leased", lease=lease, fence=lease.fence, revision=state.revision + 1)
    return LeaseGrant(result, token)


def begin_dispatch(
    state: StreamState, *, token: str, fence: int, expected_revision: int, clock: Clock, evidence: FreshnessEvidence
) -> StreamState:
    cas(state, expected_revision)
    now = utc(clock.now())
    live_lease(state, token, fence, now)
    if state.phase != "leased":
        raise StreamError("intent_already_dispatched_or_unknown")
    validate_freshness(state, evidence, "dispatch", now)
    dispatch = fingerprint(
        [
            state.scope.outbox_id,
            state.intent.operation_id,
            state.intent.payload_fingerprint,
            fence,
            evidence.transaction_id,
            evidence.run_payload_fingerprint,
        ]
    )
    return replace(
        state,
        phase="dispatched",
        revision=state.revision + 1,
        attempts=state.attempts + 1,
        dispatch_fingerprint=dispatch,
    )


def renew(
    state: StreamState, *, token: str, fence: int, expected_revision: int, clock: Clock, ttl: timedelta
) -> StreamState:
    cas(state, expected_revision)
    now = utc(clock.now())
    live_lease(state, token, fence, now)
    _duration(ttl)
    if state.phase not in {"leased", "dispatched"} or now + ttl <= state.lease.expires_at:
        raise StreamError("lease_not_renewable")
    return replace(state, lease=replace(state.lease, expires_at=now + ttl), revision=state.revision + 1)


def acknowledge(
    state: StreamState, receipt: StreamReceipt, *, token: str, fence: int, expected_revision: int, clock: Clock
) -> StreamState:
    cas(state, expected_revision)
    live_lease(state, token, fence, utc(clock.now()))
    if state.phase != "dispatched":
        raise StreamError("intent_not_dispatched")
    bound_receipt(state, receipt, delivered=True)
    return _settle(state, receipt, True)


def reject(
    state: StreamState, receipt: StreamReceipt, *, token: str, fence: int, expected_revision: int, clock: Clock
) -> StreamState:
    cas(state, expected_revision)
    live_lease(state, token, fence, utc(clock.now()))
    if state.phase != "dispatched" or not isinstance(receipt, StreamReceipt) or receipt.evidence_ref is None:
        raise StreamError("verified_refusal_required")
    bound_receipt(state, receipt, delivered=False)
    return _settle(state, receipt, False)


def mark_uncertain(state: StreamState, *, token: str, fence: int, expected_revision: int, clock: Clock) -> StreamState:
    cas(state, expected_revision)
    live_lease(state, token, fence, utc(clock.now()))
    if state.phase != "dispatched":
        raise StreamError("intent_not_dispatched")
    return replace(state, phase="uncertain", lease=None, revision=state.revision + 1)


def recover_expired(state: StreamState, *, expected_revision: int, clock: Clock) -> StreamState:
    cas(state, expected_revision)
    if state.lease is None or utc(clock.now()) < state.lease.expires_at:
        raise StreamError("lease_not_expired")
    if state.phase not in {"leased", "dispatched"}:
        raise StreamError("intent_not_in_flight")
    phase = "prepared" if state.phase == "leased" else "uncertain"
    return replace(state, phase=phase, lease=None, revision=state.revision + 1)


def reconcile(state: StreamState, receipt: StreamReceipt, *, delivered: bool, expected_revision: int) -> StreamState:
    cas(state, expected_revision)
    if (
        state.phase != "uncertain"
        or type(delivered) is not bool
        or not isinstance(receipt, StreamReceipt)
        or receipt.evidence_ref is None
    ):
        raise StreamError("verified_reconciliation_required")
    bound_receipt(state, receipt, delivered=delivered)
    return _settle(state, receipt, delivered)


def _settle(state: StreamState, receipt: StreamReceipt, delivered: bool) -> StreamState:
    return replace(
        state,
        phase="acked" if delivered else "rejected",
        lease=None,
        revision=state.revision + 1,
        card_id=receipt.card_id if delivered and state.intent.kind == "create" else state.card_id,
        message_id=receipt.message_id if delivered and state.intent.kind == "send" else state.message_id,
        last_acked_sequence=state.intent.sequence
        if delivered and state.intent.sequence is not None
        else state.last_acked_sequence,
        evidence_ref=receipt.evidence_ref,
    )

"""Renewal, stale CAS and unknown outcomes never create implicit sending permission."""

from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.stream_outbox_v2 import (
    StreamError,
    acknowledge,
    begin_dispatch,
    claim,
    fallback_intent,
    mark_uncertain,
    next_intent,
    reconcile,
    recover_expired,
    reject,
    renew,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock
from tests.v4.p9_v2.coverage_support_acceptance_mod import (
    AT,
    DIGEST,
    SCOPE,
    TEXT,
    TOKEN,
    TTL,
    acquire,
    dispatch,
    evidence,
    prepared,
    receipt,
)


@pytest.mark.parametrize("age", [timedelta(0), timedelta(days=1), timedelta(days=367)])
@pytest.mark.parametrize("action", ["claim", "dispatch", "renew", "ack", "reject", "uncertain", "recover", "next"])
def test_unknown_is_not_unlocked_by_time_fresh_evidence_or_any_public_transition(age: timedelta, action: str) -> None:
    clock = FrozenClock(AT)
    sent = dispatch(acquire(prepared("close"), clock), clock)
    unknown = restore_state(state_metadata(sent), scope=SCOPE)
    clock.advance(age)
    values = dict(token=TOKEN, fence=unknown.fence, expected_revision=unknown.revision, clock=clock)
    operations = {
        "claim": lambda: acquire(unknown, clock),
        "dispatch": lambda: dispatch(unknown, clock),
        "renew": lambda: renew(unknown, **values, ttl=TTL),
        "ack": lambda: acknowledge(unknown, receipt(unknown), **values),
        "reject": lambda: reject(unknown, receipt(unknown, delivered=False), **values),
        "uncertain": lambda: mark_uncertain(unknown, **values),
        "recover": lambda: recover_expired(unknown, expected_revision=unknown.revision, clock=clock),
        "next": lambda: next_intent(
            unknown,
            operation_id="different-key",
            kind="close",
            payload_fingerprint=DIGEST,
            expected_revision=unknown.revision,
        ),
    }
    with pytest.raises(StreamError):
        operations[action]()
    assert unknown.phase == "uncertain" and unknown.lease is None and unknown.attempts == 1
    assert fallback_intent(unknown) is None


@pytest.mark.parametrize("kind", ["create", "send", "update", "close"])
def test_renewal_preserves_fence_but_old_revision_cannot_dispatch(kind: str) -> None:
    clock = FrozenClock(AT)
    leased = acquire(prepared(kind), clock)
    old_proof = evidence(leased, "dispatch", clock)
    clock.advance(timedelta(seconds=1))
    extended = renew(leased, token=TOKEN, fence=leased.fence, expected_revision=leased.revision, clock=clock, ttl=TTL)
    assert extended.fence == leased.fence and extended.lease.expires_at == AT + timedelta(seconds=61)
    with pytest.raises(StreamError) as caught:
        begin_dispatch(
            extended,
            token=TOKEN,
            fence=leased.fence,
            expected_revision=leased.revision,
            clock=clock,
            evidence=old_proof,
        )
    assert caught.value.reason_code == "revision_conflict"
    assert dispatch(extended, clock).phase == "dispatched"


def test_dispatched_renewal_fences_delayed_ack_revision_without_changing_reserved_sequence() -> None:
    clock = FrozenClock(AT)
    sent = dispatch(acquire(prepared("update"), clock), clock)
    clock.advance(timedelta(seconds=1))
    extended = renew(sent, token=TOKEN, fence=sent.fence, expected_revision=sent.revision, clock=clock, ttl=TTL)
    assert extended.intent.sequence == sent.intent.sequence and extended.attempts == sent.attempts
    with pytest.raises(StreamError):
        acknowledge(
            extended, receipt(sent), token=TOKEN, fence=sent.fence, expected_revision=sent.revision, clock=clock
        )
    settled = acknowledge(
        extended, receipt(extended), token=TOKEN, fence=extended.fence, expected_revision=extended.revision, clock=clock
    )
    assert settled.phase == "acked" and settled.last_acked_sequence == sent.intent.sequence


@pytest.mark.parametrize(
    "ttl", [timedelta(0), timedelta(microseconds=-1), timedelta(minutes=10, microseconds=1), None, 60]
)
def test_claim_and_renew_refuse_invalid_lease_durations(ttl: object) -> None:
    clock, state = FrozenClock(AT), prepared()
    with pytest.raises(StreamError):
        acquire(state, clock, ttl=ttl)
    leased = acquire(state, clock)
    with pytest.raises(StreamError):
        renew(leased, token=TOKEN, fence=leased.fence, expected_revision=leased.revision, clock=clock, ttl=ttl)


def test_zero_extension_is_refused_but_exact_ten_minute_duration_is_accepted() -> None:
    clock, state = FrozenClock(AT), prepared()
    leased = acquire(state, clock, ttl=timedelta(minutes=10))
    with pytest.raises(StreamError) as caught:
        renew(
            leased,
            token=TOKEN,
            fence=leased.fence,
            expected_revision=leased.revision,
            clock=clock,
            ttl=timedelta(minutes=10),
        )
    assert caught.value.reason_code == "lease_not_renewable"


@pytest.mark.parametrize("action", ["ack", "reject", "uncertain"])
def test_a_live_claim_alone_cannot_be_settled_as_if_transport_had_started(action: str) -> None:
    clock = FrozenClock(AT)
    state = acquire(prepared(), clock)
    values = dict(token=TOKEN, fence=state.fence, expected_revision=state.revision, clock=clock)
    operations = {
        "ack": lambda: acknowledge(state, receipt(state), **values),
        "reject": lambda: reject(state, receipt(state, delivered=False), **values),
        "uncertain": lambda: mark_uncertain(state, **values),
    }
    with pytest.raises(StreamError):
        operations[action]()
    assert state.phase == "leased" and state.attempts == 0


@pytest.mark.parametrize("field", tuple(SCOPE.__dataclass_fields__))
def test_unknown_reconciliation_requires_every_original_scope_binding(field: str) -> None:
    clock = FrozenClock(AT)
    sent = dispatch(acquire(prepared("close"), clock), clock)
    unknown = restore_state(state_metadata(sent), scope=SCOPE)
    forged = replace(receipt(unknown), scope=replace(SCOPE, **{field: "foreign-value"}))
    with pytest.raises(StreamError) as caught:
        reconcile(unknown, forged, delivered=True, expected_revision=unknown.revision)
    assert caught.value.reason_code == "receipt_scope_mismatch"
    assert TEXT not in str(caught.value) and "foreign-value" not in str(caught.value)


@pytest.mark.parametrize("delivered", [None, 0, 1, "false", "true"])
def test_truthy_delivery_values_cannot_settle_unknown_state(delivered: object) -> None:
    clock = FrozenClock(AT)
    unknown = restore_state(state_metadata(dispatch(acquire(prepared("close"), clock), clock)), scope=SCOPE)
    with pytest.raises(StreamError):
        reconcile(unknown, receipt(unknown), delivered=delivered, expected_revision=unknown.revision)


@pytest.mark.parametrize("kind", ["create", "send"])
def test_confirmed_refusal_cannot_smuggle_an_unexpected_success_remote_identity(kind: str) -> None:
    clock = FrozenClock(AT)
    state = dispatch(acquire(prepared(kind), clock), clock)
    with pytest.raises(StreamError) as caught:
        reject(
            state,
            receipt(state, delivered=True),
            token=TOKEN,
            fence=state.fence,
            expected_revision=state.revision,
            clock=clock,
        )
    assert caught.value.reason_code == "unsent_evidence_has_unexpected_remote_receipt"
    assert fallback_intent(state) is None


@pytest.mark.parametrize("kind,changes", [("create", {"card_id": None}), ("send", {"message_id": None})])
def test_success_receipt_must_include_the_remote_identity_created_by_its_stage(kind: str, changes: dict) -> None:
    clock = FrozenClock(AT)
    state = dispatch(acquire(prepared(kind), clock), clock)
    with pytest.raises(StreamError):
        acknowledge(
            state,
            replace(receipt(state), **changes),
            token=TOKEN,
            fence=state.fence,
            expected_revision=state.revision,
            clock=clock,
        )


@pytest.mark.parametrize("attempts", [0, True, 11])
def test_attempt_limit_configuration_cannot_enable_unbounded_implicit_retries(attempts: object) -> None:
    clock, state = FrozenClock(AT), prepared()
    with pytest.raises(StreamError):
        claim(
            state,
            token=TOKEN,
            worker_id="worker",
            clock=clock,
            ttl=TTL,
            evidence=evidence(state, "claim", clock),
            expected_revision=state.revision,
            max_attempts=attempts,
        )

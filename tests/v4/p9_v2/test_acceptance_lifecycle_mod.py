"""Independent fenced lifecycle, crash recovery and same-card sequence invariants."""

from dataclasses import replace
from datetime import timedelta
from random import Random

import pytest
from test_acceptance_stream_mod import AT, SCOPE, TTL, complete, dispatched, leased, prepared, proof, receipt

from mingjing_core.adapters.channels.stream_outbox_v2 import (
    StreamError,
    acknowledge,
    begin_dispatch,
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


def streaming(clock):
    state = complete(prepared(), clock)
    state = next_intent(
        state, operation_id="send-one", kind="send", payload_fingerprint="d" * 64, expected_revision=state.revision
    )
    return complete(state, clock)


def closed_or_updating(clock, kind="close"):
    state = streaming(clock)
    return next_intent(
        state, operation_id=kind + "-one", kind=kind, payload_fingerprint="e" * 64, expected_revision=state.revision
    )


def test_expired_unstarted_claim_can_be_recovered_but_old_fence_cannot_act():
    clock = FrozenClock(AT)
    first = leased(prepared(), clock, "first-secret")
    clock.advance(TTL)
    recovered = recover_expired(first.state, expected_revision=first.state.revision, clock=clock)
    assert recovered.phase == "prepared"
    second = leased(recovered, clock, "second-secret")
    assert second.state.fence > first.state.fence
    with pytest.raises(StreamError):
        renew(
            second.state,
            token=first.token,
            fence=first.state.fence,
            expected_revision=second.state.revision,
            clock=clock,
            ttl=TTL,
        )
    with pytest.raises(StreamError):
        begin_dispatch(
            second.state,
            token=first.token,
            fence=first.state.fence,
            expected_revision=second.state.revision,
            clock=clock,
            evidence=proof(second.state, "dispatch", clock),
        )


def test_lease_is_invalid_at_exact_expiry_and_cannot_be_renewed_back_to_life():
    clock, state = FrozenClock(AT), prepared()
    grant = leased(state, clock)
    clock.advance(TTL)
    with pytest.raises(StreamError):
        begin_dispatch(
            grant.state,
            token=grant.token,
            fence=grant.state.fence,
            expected_revision=grant.state.revision,
            clock=clock,
            evidence=proof(grant.state, "dispatch", clock),
        )
    with pytest.raises(StreamError):
        renew(
            grant.state,
            token=grant.token,
            fence=grant.state.fence,
            expected_revision=grant.state.revision,
            clock=clock,
            ttl=TTL,
        )


def test_dispatch_started_expiry_or_crash_is_unknown_and_never_blindly_resent():
    clock = FrozenClock(AT)
    state, grant = dispatched(prepared(), clock)
    crashed = restore_state(state_metadata(state), scope=SCOPE)
    assert crashed.phase == "uncertain" and crashed.lease is None
    clock.advance(TTL)
    expired = recover_expired(state, expected_revision=state.revision, clock=clock)
    assert expired.phase == "uncertain"
    for unknown in (crashed, expired):
        for advance in (0, 1, 1000):
            clock.advance(timedelta(days=advance))
            with pytest.raises(StreamError):
                leased(unknown, clock, "another-secret")
            with pytest.raises(StreamError):
                next_intent(
                    unknown,
                    operation_id="another-operation",
                    kind="create",
                    payload_fingerprint="f" * 64,
                    expected_revision=unknown.revision,
                )
            assert fallback_intent(unknown) is None
    assert grant.token not in repr(state_metadata(state))
    assert SCOPE.target not in repr(state_metadata(state))


def test_each_successful_update_and_close_reuses_card_and_increments_reserved_sequence():
    clock = FrozenClock(AT)
    state = streaming(clock)
    assert state.card_id == "card-one" and state.message_id == "remote-message"
    for sequence in range(1, 11):
        state = next_intent(
            state,
            operation_id=f"update-{sequence}",
            kind="update",
            payload_fingerprint="e" * 64,
            expected_revision=state.revision,
        )
        assert state.intent.sequence == sequence and state.last_reserved_sequence == sequence
        state = complete(state, clock)
        assert state.last_acked_sequence == sequence and state.card_id == "card-one"
    state = next_intent(
        state, operation_id="close", kind="close", payload_fingerprint="e" * 64, expected_revision=state.revision
    )
    assert state.intent.sequence == 11
    state = complete(state, clock)
    assert state.phase == "acked" and state.last_acked_sequence == 11
    with pytest.raises(StreamError):
        next_intent(
            state,
            operation_id="late-update",
            kind="update",
            payload_fingerprint="e" * 64,
            expected_revision=state.revision,
        )


@pytest.mark.parametrize("field", list(SCOPE.__dataclass_fields__))
def test_receipt_scope_evidence_is_bound_to_all_seven_delivery_identifiers(field):
    clock = FrozenClock(AT)
    state, grant = dispatched(closed_or_updating(clock, "update"), clock)
    forged = receipt(state, scope=replace(SCOPE, **{field: "other"}))
    with pytest.raises(StreamError):
        acknowledge(state, forged, token=grant.token, fence=state.fence, expected_revision=state.revision, clock=clock)


@pytest.mark.parametrize(
    "change",
    [
        {"operation_id": "other"},
        {"payload_fingerprint": "f" * 64},
        {"sequence": 99},
        {"card_id": "other"},
        {"message_id": "other"},
    ],
)
def test_receipt_cannot_settle_a_different_payload_card_operation_or_sequence(change):
    clock = FrozenClock(AT)
    state, grant = dispatched(closed_or_updating(clock, "update"), clock)
    with pytest.raises(StreamError):
        acknowledge(
            state,
            receipt(state, **change),
            token=grant.token,
            fence=state.fence,
            expected_revision=state.revision,
            clock=clock,
        )


def test_only_explicit_close_refusal_with_bound_evidence_produces_a_fallback_intent():
    clock = FrozenClock(AT)
    state, grant = dispatched(closed_or_updating(clock), clock)
    unknown = mark_uncertain(state, token=grant.token, fence=state.fence, expected_revision=state.revision, clock=clock)
    assert fallback_intent(unknown) is None and fallback_intent(state) is None
    with pytest.raises(StreamError):
        reject(
            state,
            receipt(state, evidence_ref=None),
            token=grant.token,
            fence=state.fence,
            expected_revision=state.revision,
            clock=clock,
        )
    rejected = reject(
        state, receipt(state), token=grant.token, fence=state.fence, expected_revision=state.revision, clock=clock
    )
    fallback = fallback_intent(rejected)
    assert fallback is not None and fallback.kind == "fallback"
    assert fallback.payload_fingerprint == state.intent.payload_fingerprint
    assert fallback == fallback_intent(rejected)
    confirmed_unsent = reconcile(unknown, receipt(unknown), delivered=False, expected_revision=unknown.revision)
    assert fallback_intent(confirmed_unsent) == fallback
    update, lease = dispatched(closed_or_updating(clock, "update"), clock)
    refusal = reject(
        update, receipt(update), token=lease.token, fence=update.fence, expected_revision=update.revision, clock=clock
    )
    assert fallback_intent(refusal) is None


@pytest.mark.parametrize("seed", range(40))
def test_1000_frozen_clock_random_dispatch_crash_paths_preserve_fencing_and_no_resend(seed):
    rng = Random(409922 + seed)
    for _ in range(25):
        clock = FrozenClock(AT)
        grant = leased(prepared(), clock)
        offset = rng.randrange(0, 63)
        clock.advance(timedelta(seconds=offset))
        if offset >= 60:
            with pytest.raises(StreamError):
                begin_dispatch(
                    grant.state,
                    token=grant.token,
                    fence=grant.state.fence,
                    expected_revision=grant.state.revision,
                    clock=clock,
                    evidence=proof(grant.state, "dispatch", clock),
                )
            continue
        state = begin_dispatch(
            grant.state,
            token=grant.token,
            fence=grant.state.fence,
            expected_revision=grant.state.revision,
            clock=clock,
            evidence=proof(grant.state, "dispatch", clock),
        )
        if rng.randrange(3) == 0:
            done = acknowledge(
                state,
                receipt(state),
                token=grant.token,
                fence=state.fence,
                expected_revision=state.revision,
                clock=clock,
            )
            assert done.phase == "acked"
            with pytest.raises(StreamError):
                leased(done, clock)
        else:
            unknown = restore_state(state_metadata(state), scope=SCOPE)
            assert unknown.phase == "uncertain" and unknown.attempts == 1
            with pytest.raises(StreamError):
                leased(unknown, clock)
            assert fallback_intent(unknown) is None

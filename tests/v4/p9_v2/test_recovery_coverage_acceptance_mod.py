"""Restore keeps exact capabilities and cannot erase incompatible persisted history."""

import copy
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from mingjing_core.adapters.channels.stream_outbox_v2 import (
    StreamError,
    StreamState,
    mark_uncertain,
    next_intent,
    recover_expired,
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
    settle,
)


@pytest.mark.parametrize("kind", ["create", "send", "update", "close"])
@pytest.mark.parametrize("phase", ["prepared", "leased", "dispatched", "acked", "rejected", "uncertain"])
def test_each_legitimate_snapshot_restores_without_creating_an_extra_permission(kind: str, phase: str) -> None:
    clock, state = FrozenClock(AT), prepared(kind)
    if phase != "prepared":
        state = acquire(state, clock)
    if phase not in {"prepared", "leased"}:
        state = dispatch(state, clock)
    if phase in {"acked", "rejected"}:
        state = settle(state, clock, delivered=phase == "acked")
    elif phase == "uncertain":
        state = mark_uncertain(state, token=TOKEN, fence=state.fence, expected_revision=state.revision, clock=clock)
    raw = state_metadata(state)
    frozen = copy.deepcopy(raw)
    restored = restore_state(raw, scope=SCOPE)
    expected = (
        replace(state, phase="uncertain", lease=None, revision=state.revision + 1) if phase == "dispatched" else state
    )
    assert restored == expected and raw == frozen
    serialized = json.dumps(raw)
    assert TEXT not in serialized and TOKEN not in serialized and SCOPE.target not in serialized


def test_restored_live_lease_keeps_original_secret_and_requires_fresh_dispatch_evidence() -> None:
    clock = FrozenClock(AT)
    state = acquire(prepared("update"), clock)
    restored = restore_state(state_metadata(state), scope=SCOPE)
    with pytest.raises(StreamError) as caught:
        dispatch(restored, clock, token="different-worker-secret")
    assert caught.value.reason_code == "lease_token_conflict"
    clock.advance(timedelta(microseconds=1))
    with pytest.raises(StreamError):
        dispatch(restored, clock, proof=evidence(state, "claim", clock))
    assert dispatch(restored, clock).phase == "dispatched"


def test_restored_expired_unsent_lease_requires_new_fence_and_cannot_keep_old_capability() -> None:
    clock = FrozenClock(AT)
    original = acquire(prepared("update"), clock)
    restored = restore_state(state_metadata(original), scope=SCOPE)
    clock.advance(TTL)
    recovered = recover_expired(restored, expected_revision=restored.revision, clock=clock)
    replacement = acquire(recovered, clock, token="new-secret")
    assert replacement.fence == original.fence + 1 and replacement.attempts == 0
    with pytest.raises(StreamError):
        dispatch(replacement, clock, token=TOKEN)
    assert dispatch(replacement, clock, token="new-secret").attempts == 1


def state_with_history() -> StreamState:
    clock = FrozenClock(AT)
    acknowledged = settle(dispatch(acquire(prepared("update"), clock), clock), clock)
    return next_intent(
        acknowledged,
        operation_id="fictional-update-two",
        kind="update",
        payload_fingerprint=DIGEST,
        expected_revision=acknowledged.revision,
    )


def test_future_acked_sequence_in_history_cannot_restore_as_lower_sendable_current_intent() -> None:
    state = state_with_history()
    raw = state_metadata(state)
    assert raw["history"][-1]["status"] == "acked"
    raw["history"][-1]["intent"]["sequence"] = raw["last_reserved_sequence"] + 1
    unchanged = copy.deepcopy(raw)
    with pytest.raises(StreamError):
        restore_state(raw, scope=SCOPE)
    assert raw == unchanged


@pytest.mark.parametrize("kind", ["update", "close"])
def test_history_cannot_claim_a_later_sequence_even_when_current_operation_is_settled(kind: str) -> None:
    clock = FrozenClock(AT)
    state = state_with_history()
    acknowledged = settle(dispatch(acquire(state, clock), clock), clock)
    raw = state_metadata(acknowledged)
    raw["history"][0]["intent"].update(kind=kind, sequence=raw["last_reserved_sequence"] + 1)
    with pytest.raises(StreamError):
        restore_state(raw, scope=SCOPE)


@pytest.mark.parametrize("change", ["reverse", "repeat"])
def test_history_reservations_cannot_reverse_or_reuse_prior_sequence(change: str) -> None:
    clock = FrozenClock(AT)
    acknowledged = settle(dispatch(acquire(state_with_history(), clock), clock), clock)
    state = next_intent(
        acknowledged,
        operation_id="fictional-update-three",
        kind="update",
        payload_fingerprint=DIGEST,
        expected_revision=acknowledged.revision,
    )
    raw = state_metadata(state)
    sequences = [2, 1] if change == "reverse" else [1, 1]
    for record, sequence in zip(raw["history"], sequences, strict=True):
        record["intent"]["sequence"] = sequence
    with pytest.raises(StreamError):
        restore_state(raw, scope=SCOPE)


def test_confirmed_refusal_history_can_leave_sequence_gaps_without_becoming_unknown() -> None:
    clock = FrozenClock(AT)
    refused = settle(dispatch(acquire(prepared("update"), clock), clock), clock, delivered=False)
    state = next_intent(
        refused,
        operation_id="fictional-update-after-refusal",
        kind="update",
        payload_fingerprint=DIGEST,
        expected_revision=refused.revision,
    )
    assert state.intent.sequence == 2 and state.last_acked_sequence == 0
    acknowledged = settle(dispatch(acquire(state, clock), clock), clock)
    assert acknowledged.last_acked_sequence == 2
    assert restore_state(state_metadata(acknowledged), scope=SCOPE) == acknowledged

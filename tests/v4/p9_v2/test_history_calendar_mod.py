"""Known history is ordered and bounded; checkpoint bootstrap never requires a complete prefix.

Frozen independent truth: sequence gaps and absent earlier records are valid, but known sequenced
records must increase strictly before the current sequence; an ack cannot exceed last_acked.
All capability and remote identifiers below are fictional, and no transport is configured.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from mingjing_core.adapters.channels.cardkit_contracts import (
    CardCheckpoint,
    CardScope,
    fingerprint,
)
from mingjing_core.adapters.channels.stream_outbox_v2 import (
    FreshnessEvidence,
    StreamError,
    StreamReceipt,
    StreamScope,
    StreamState,
    VersionEvidence,
    acknowledge,
    begin_dispatch,
    claim,
    fallback_intent,
    next_intent,
    prepare_intent,
    reject,
    restore_state,
    state_metadata,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, 1, 20, tzinfo=UTC)
SCOPE = StreamScope(
    "history-owner",
    "history-self",
    "history-box",
    "history-run",
    "history-biz",
    "feishu",
    "ou_fake",
)
TOKEN = "SYNTHETIC_HISTORY_CAPABILITY"
DIGEST = "a" * 64


def evidence(state: StreamState, clock: FrozenClock, purpose: str) -> FreshnessEvidence:
    body = {
        "schema": "core4.0",
        "message_id": "synthetic-history-message",
        "text": "SYNTHETIC_OFFLINE_HISTORY",
        "receipts": [],
        "used_fact_ids": [],
        "used_claim_ids": [],
        "asked": None,
        "options": None,
        "review": {"state": "passed", "reasons": []},
        "usage": {},
        "validation": {"status": "validated", "valid": True, "schema": "core4.0"},
        "meta": {
            "core_run": {"run_id": SCOPE.run_id, "operation_id": "synthetic-runtime"},
            "subject_id": SCOPE.subject_id,
            "case_ids": [],
            "structural_warnings": [],
        },
    }
    versions = (
        VersionEvidence("source", "synthetic-source", DIGEST, DIGEST),
        VersionEvidence("dependency", "synthetic-profile", DIGEST, DIGEST),
    )
    return FreshnessEvidence(
        state.scope,
        state.intent.operation_id,
        state.revision,
        purpose,
        clock.now(),
        "synthetic-transaction-" + purpose,
        "succeeded",
        state.intent.payload_fingerprint,
        fingerprint(body),
        body,
        versions,
        4,
        4,
        tuple((item.category, item.identity, item.expected_hash) for item in versions),
    )


def dispatch(state: StreamState, clock: FrozenClock) -> StreamState:
    grant = claim(
        state,
        token=TOKEN,
        worker_id="synthetic-worker",
        clock=clock,
        ttl=timedelta(minutes=1),
        evidence=evidence(state, clock, "claim"),
        expected_revision=state.revision,
    )
    return begin_dispatch(
        grant.state,
        token=TOKEN,
        fence=grant.state.fence,
        expected_revision=grant.state.revision,
        clock=clock,
        evidence=evidence(grant.state, clock, "dispatch"),
    )


def finish(state: StreamState, clock: FrozenClock, *, delivered: bool = True) -> StreamState:
    state = dispatch(state, clock)
    receipt = StreamReceipt(
        state.scope,
        state.intent.operation_id,
        state.intent.payload_fingerprint,
        state.intent.sequence,
        "synthetic-card" if state.intent.kind == "create" else state.card_id,
        "synthetic-message" if state.intent.kind == "send" else state.message_id,
        "synthetic-confirmed-remote-evidence",
    )
    operation = acknowledge if delivered else reject
    return operation(
        state,
        receipt,
        token=TOKEN,
        fence=state.fence,
        expected_revision=state.revision,
        clock=clock,
    )


def checkpoint_start(reserved: int = 0, acked: int = 0) -> StreamState:
    checkpoint = CardCheckpoint(
        CardScope(SCOPE.owner_id, SCOPE.subject_id, SCOPE.target, SCOPE.business_id),
        phase="streaming",
        card_id="synthetic-card",
        message_id="synthetic-message",
        initial_fingerprint=DIGEST,
        last_reserved_sequence=reserved,
        last_acked_sequence=acked,
    )
    return prepare_intent(
        SCOPE,
        operation_id=f"synthetic-update-{reserved + 1}",
        kind="update",
        payload_fingerprint=DIGEST,
        checkpoint=checkpoint,
    )


def advance(state: StreamState, operation_id: str) -> StreamState:
    return next_intent(
        state,
        operation_id=operation_id,
        kind="update",
        payload_fingerprint=DIGEST,
        expected_revision=state.revision,
    )


def ready(outcomes: tuple[bool, ...]) -> StreamState:
    state, clock = checkpoint_start(), FrozenClock(AT)
    for number, delivered in enumerate(outcomes, 2):
        state = advance(finish(state, clock, delivered=delivered), f"synthetic-update-{number}")
    return state


@pytest.mark.parametrize("forged_sequence", (2, 3, 50))
def test_known_historical_ack_must_precede_current_sequence(
    forged_sequence: int,
) -> None:
    state = ready((True,))
    data = state_metadata(state)
    assert state.intent.sequence == 2 and state.last_acked_sequence == 1
    data["history"][0]["intent"]["sequence"] = forged_sequence
    with pytest.raises(StreamError):
        restore_state(data, scope=SCOPE)


def test_known_ack_cannot_exceed_last_acked_even_when_before_current() -> None:
    state = ready((True, False))
    data = state_metadata(state)
    assert state.intent.sequence == 3 and state.last_acked_sequence == 1
    data["history"] = [data["history"][0]]
    data["history"][0]["intent"]["sequence"] = 2
    with pytest.raises(StreamError):
        restore_state(data, scope=SCOPE)


@pytest.mark.parametrize("sequences", ((2, 1, 3), (1, 1, 3), (1, 3, 2)))
def test_known_history_sequences_are_strictly_increasing(
    sequences: tuple[int, ...],
) -> None:
    data = state_metadata(ready((True, True, True)))
    for item, sequence in zip(data["history"], sequences, strict=True):
        item["intent"]["sequence"] = sequence
    with pytest.raises(StreamError):
        restore_state(data, scope=SCOPE)


@pytest.mark.parametrize("forged_sequence", (3, 4, 90))
def test_known_rejection_must_also_precede_current_sequence(
    forged_sequence: int,
) -> None:
    data = state_metadata(ready((True, False)))
    data["history"][1]["intent"]["sequence"] = forged_sequence
    with pytest.raises(StreamError):
        restore_state(data, scope=SCOPE)


@pytest.mark.parametrize("reserved,acked", ((0, 0), (40, 38), (40, 40), (999, 995)))
def test_bootstrap_checkpoint_needs_no_earlier_history(reserved: int, acked: int) -> None:
    state = checkpoint_start(reserved, acked)
    restored = restore_state(state_metadata(state), scope=SCOPE)
    assert restored.history == () and restored.intent.sequence == reserved + 1
    assert restored.last_acked_sequence == acked
    assert dispatch(restored, FrozenClock(AT)).phase == "dispatched"


@pytest.mark.parametrize("omitted", ((), (1,), (1, 2), (0, 1, 2)))
def test_rejected_gaps_and_partial_known_history_do_not_require_prefix(
    omitted: tuple[int, ...],
) -> None:
    data = state_metadata(ready((True, False, False, True)))
    data["history"] = [item for index, item in enumerate(data["history"]) if index not in omitted]
    restored = restore_state(data, scope=SCOPE)
    assert restored.intent.sequence == 5 and restored.last_acked_sequence == 4
    assert dispatch(restored, FrozenClock(AT)).intent.sequence == 5


def test_full_public_create_send_updates_preserve_unsequenced_history() -> None:
    clock = FrozenClock(AT)
    state = prepare_intent(
        SCOPE,
        operation_id="synthetic-create",
        kind="create",
        payload_fingerprint=DIGEST,
    )
    state = finish(state, clock)
    state = next_intent(
        state,
        operation_id="synthetic-send",
        kind="send",
        payload_fingerprint=DIGEST,
        expected_revision=state.revision,
    )
    state = advance(finish(state, clock), "synthetic-first-update")
    state = advance(finish(state, clock), "synthetic-second-update")
    restored = restore_state(state_metadata(state), scope=SCOPE)
    assert [item.intent.sequence for item in restored.history] == [None, None, 1]
    assert finish(restored, clock).last_acked_sequence == 2


@pytest.mark.parametrize("outcomes", ((True,), (True, False), (True, False, False, True)))
def test_unknown_after_history_restore_never_automatically_resends(
    outcomes: tuple[bool, ...],
) -> None:
    clock = FrozenClock(AT)
    state = dispatch(ready(outcomes), clock)
    unknown = restore_state(state_metadata(state), scope=SCOPE)
    assert unknown.phase == "uncertain" and unknown.lease is None
    assert fallback_intent(unknown) is None
    with pytest.raises(StreamError):
        dispatch(unknown, clock)
    with pytest.raises(StreamError):
        advance(unknown, "synthetic-forbidden-retry")


def test_restoring_valid_history_does_not_mutate_metadata_input() -> None:
    data = state_metadata(ready((True, False, True)))
    before: dict[str, Any] = {
        "sequences": [item["intent"]["sequence"] for item in data["history"]],
        "statuses": [item["status"] for item in data["history"]],
    }
    restored = restore_state(data, scope=SCOPE)
    assert [item["intent"]["sequence"] for item in data["history"]] == before["sequences"]
    assert [item["status"] for item in data["history"]] == before["statuses"]
    assert restored.last_acked_sequence == 3

"""Revision fencing, terminal states and retention proofs under explicit frozen time."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.streaming.cleanup import (
    CommittedRun,
    StoredEventMetadata,
    metadata_for_cleanup,
    plan_delta_cleanup,
)
from mingjing_core.streaming.coalescer import DeltaBuffer, DeltaPolicy, feed_delta, poll_delta, replace_text
from mingjing_core.streaming.heartbeat import HeartbeatState, heartbeat_tick
from mingjing_core.streaming.stream_clock import StreamStateError
from mingjing_core.streaming.text_projection import TextProjection, reduce_event
from mingjing_core.timekit.clock import FrozenClock
from tests.v4.streaming.coverage_support_acceptance_mod import AT, SCOPE, event


@pytest.mark.parametrize("field", ["max_chars", "max_delay_ms"])
@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "40", 200_001])
def test_invalid_batch_policies_do_not_disable_flush_boundaries(field: str, value: object) -> None:
    with pytest.raises(StreamStateError):
        DeltaPolicy(**{field: value})


@pytest.mark.parametrize(
    "fields",
    [
        {"scope": None},
        {"text": 1},
        {"text": "x" * 200_001},
        {"generation": True},
        {"generation": -1},
        {"text": "buffer", "opened_at": None},
        {"opened_at": AT},
        {"text": "buffer", "opened_at": AT, "last_observed_at": AT - timedelta(microseconds=1)},
        {"text": "buffer", "opened_at": AT.replace(tzinfo=None)},
    ],
)
def test_buffer_constructor_rejects_inconsistent_recovery_snapshots(fields: dict[str, Any]) -> None:
    with pytest.raises(StreamStateError):
        DeltaBuffer(**({"scope": SCOPE} | fields))


@pytest.mark.parametrize("chunk", [None, 1, b"bytes", "x" * 200_001], ids=["none", "int", "bytes", "oversized"])
def test_nontext_or_oversized_input_never_changes_a_valid_buffer(chunk: object) -> None:
    buffer = DeltaBuffer(SCOPE)
    with pytest.raises(StreamStateError):
        feed_delta(buffer, chunk, generation=0, clock=FrozenClock(AT))
    assert buffer.text == "" and buffer.generation == 0


def test_reset_without_revision_discards_expired_buffer_instead_of_publishing_old_draft() -> None:
    clock = FrozenClock(AT)
    old = feed_delta(DeltaBuffer(SCOPE), "虚构旧草稿", generation=0, clock=clock).state
    clock.advance(timedelta(seconds=1))
    reset = replace_text(old, "虚构修订", reason="resumed", clock=clock)
    assert [draft.type for draft in reset.drafts] == ["text_reset"]
    assert dict(reset.drafts[0].payload) == {"text": "虚构修订", "reason": "resumed"}
    assert not poll_delta(reset.state, clock=clock).drafts
    with pytest.raises(StreamStateError):
        feed_delta(reset.state, "迟到旧流", generation=0, clock=clock)
    assert feed_delta(reset.state, "新流", generation=1, clock=clock).state.text == "新流"


@pytest.mark.parametrize(
    "fields", [{"last_seq": True}, {"last_seq": -1}, {"scope": None}, {"terminal": 1}, {"text": 1}]
)
def test_projection_constructor_does_not_coerce_scope_sequence_or_flags(fields: dict[str, Any]) -> None:
    with pytest.raises(StreamStateError):
        TextProjection(**({"scope": SCOPE} | fields))


def test_error_terminates_text_but_old_replay_and_idempotent_error_remain_safe() -> None:
    first, terminal = event("text_delta", 2), event("error", 9)
    initial = reduce_event(TextProjection(SCOPE), first, scope=SCOPE)
    state = reduce_event(initial, terminal, scope=SCOPE)
    assert state.terminal and state.text == initial.text
    assert reduce_event(state, terminal, scope=SCOPE) == state
    assert reduce_event(state, first, scope=SCOPE) == state
    with pytest.raises(StreamStateError):
        reduce_event(state, event("status", 10), scope=SCOPE)


@pytest.mark.parametrize(
    "kind", ["started", "status", "tool_call", "tool_result", "review", "memory_receipt", "present_options"]
)
def test_nontext_events_advance_cursor_without_overwriting_reviewed_text(kind: str) -> None:
    state = reduce_event(TextProjection(SCOPE), event("text_reset", 3), scope=SCOPE)
    next_state = reduce_event(state, event(kind, 11), scope=SCOPE)
    assert next_state.last_seq == 11 and next_state.text == state.text and next_state.revision_id == state.revision_id
    assert not next_state.terminal


@pytest.mark.parametrize("clock", [datetime(2026, 10, 21), "not-a-date", None])
def test_invalid_clock_snapshot_never_emits_heartbeat_or_draft(clock: object) -> None:
    class InvalidClock:
        def now(self) -> object:
            return clock

    with pytest.raises(StreamStateError):
        heartbeat_tick(HeartbeatState(AT), clock=InvalidClock())
    with pytest.raises(StreamStateError):
        poll_delta(DeltaBuffer(SCOPE), clock=InvalidClock())


def test_heartbeat_recovered_observation_cannot_precede_last_sent() -> None:
    with pytest.raises(StreamStateError):
        HeartbeatState(AT, AT - timedelta(microseconds=1))
    with pytest.raises(StreamStateError):
        heartbeat_tick(HeartbeatState(AT), clock=FrozenClock(AT - timedelta(microseconds=1)))


@pytest.mark.parametrize(
    "fields",
    [
        {"scope": None},
        {"message_id": ""},
        {"message_id": None},
        {"final_seq": True},
        {"final_seq": 0},
        {"revision": True},
        {"revision": 0},
        {"committed_at": AT.replace(tzinfo=None)},
    ],
)
def test_cleanup_requires_a_well_formed_commit_proof(fields: dict[str, Any]) -> None:
    with pytest.raises(StreamStateError):
        CommittedRun(**({"scope": SCOPE, "committed_at": AT, "final_seq": 9, "message_id": "message"} | fields))


@pytest.mark.parametrize(
    "fields",
    [
        {"scope": None},
        {"seq": True},
        {"seq": 0},
        {"type": ""},
        {"type": None},
        {"payload_fingerprint": "f" * 63},
        {"payload_fingerprint": "F" * 64},
        {"payload_fingerprint": None},
        {"created_at": AT.replace(tzinfo=None)},
    ],
)
def test_cleanup_metadata_cannot_silently_widen_the_deletion_scope(fields: dict[str, Any]) -> None:
    values = {"scope": SCOPE, "seq": 1, "type": "text_delta", "created_at": AT, "payload_fingerprint": "a" * 64}
    with pytest.raises(StreamStateError):
        StoredEventMetadata(**(values | fields))


def test_cleanup_rejects_untrusted_projection_and_pre_final_rows_created_after_commit() -> None:
    with pytest.raises(StreamStateError):
        metadata_for_cleanup({"seq": 1, "type": "text_delta"})
    committed = CommittedRun(SCOPE, AT, 9, "message")
    future = StoredEventMetadata(SCOPE, 1, "text_delta", AT + timedelta(microseconds=1), "a" * 64)
    with pytest.raises(StreamStateError):
        plan_delta_cleanup(committed, (future,), clock=FrozenClock(AT + timedelta(days=1)))


def test_cleanup_is_order_independent_but_fingerprint_commit_and_revision_sensitive() -> None:
    committed = CommittedRun(SCOPE, AT, 9, "message", revision=4)
    rows = tuple(StoredEventMetadata(SCOPE, seq, "text_delta", AT, str(seq) * 64) for seq in (2, 5))
    clock = FrozenClock(AT + timedelta(days=1))
    original = plan_delta_cleanup(committed, rows, clock=clock)
    assert original == plan_delta_cleanup(committed, rows[::-1], clock=clock)
    assert [row.seq for row in original.eligible_refs] == [2, 5]
    changed = (replace(rows[0], payload_fingerprint="f" * 64), rows[1])
    assert plan_delta_cleanup(committed, changed, clock=clock).operation_id != original.operation_id
    assert plan_delta_cleanup(replace(committed, revision=5), rows, clock=clock).operation_id != original.operation_id
    assert original.expected_commit_revision == 4 and rows[0].type == "text_delta"

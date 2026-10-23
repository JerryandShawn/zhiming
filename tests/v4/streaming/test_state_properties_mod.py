"""Boundary and random state properties for batching, revision fences and retention plans."""

from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from mingjing_core.streaming.cleanup import CommittedRun, StoredEventMetadata, plan_delta_cleanup
from mingjing_core.streaming.coalescer import DeltaBuffer, feed_delta, flush_delta, poll_delta, replace_text
from mingjing_core.streaming.event_models import RunScope, make_event
from mingjing_core.streaming.heartbeat import HeartbeatState, heartbeat_tick
from mingjing_core.streaming.stream_clock import StreamStateError
from mingjing_core.streaming.text_projection import TextProjection, reduce_event
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 17, tzinfo=UTC)
SCOPE = RunScope("owner", "run1")


def test_first_byte_timer_and_character_boundary():
    clock = FrozenClock(AT)
    state = feed_delta(DeltaBuffer(SCOPE), "初", generation=0, clock=clock).state
    clock.advance(timedelta(milliseconds=149))
    assert not poll_delta(state, clock=clock).drafts
    clock.advance(timedelta(milliseconds=1))
    due = poll_delta(state, clock=clock)
    assert due.drafts[0].payload["text"] == "初" and due.state.text == ""
    full = feed_delta(DeltaBuffer(SCOPE), "字" * 40, generation=0, clock=clock)
    assert len(full.drafts) == 1 and full.state.text == ""


def test_reset_discards_old_buffer_and_rejects_stale_generation():
    clock = FrozenClock(AT)
    buffered = feed_delta(DeltaBuffer(SCOPE), "未评审草稿", generation=0, clock=clock).state
    revised = replace_text(buffered, "已修订", reason="revised", revision_id="rev2", clock=clock)
    assert [draft.type for draft in revised.drafts] == ["text_reset"]
    assert revised.state.text == ""
    with pytest.raises(StreamStateError, match="旧写入者"):
        feed_delta(revised.state, "迟到片段", generation=0, clock=clock)


def test_five_hundred_random_chunk_streams_preserve_exact_text():
    rng = Random(20261021)
    for _ in range(500):
        state, sent, original, clock = DeltaBuffer(SCOPE), [], [], FrozenClock(AT)
        for _ in range(rng.randrange(1, 30)):
            chunk = "甲🙂\n乙" * rng.randrange(0, 18)
            original.append(chunk)
            clock.advance(timedelta(milliseconds=rng.randrange(0, 250)))
            emitted = feed_delta(state, chunk, generation=0, clock=clock)
            sent.extend(draft.payload["text"] for draft in emitted.drafts)
            state = emitted.state
        sent.extend(draft.payload["text"] for draft in flush_delta(state, clock=clock).drafts)
        assert "".join(sent) == "".join(original)


def test_maximum_chunk_with_preexisting_buffer_preserves_all_text():
    clock = FrozenClock(AT)
    state = feed_delta(DeltaBuffer(SCOPE), "首", generation=0, clock=clock).state
    result = feed_delta(state, "大" * 200_000, generation=0, clock=clock)
    assert "".join(draft.payload["text"] for draft in result.drafts) == "首" + "大" * 200_000


def test_heartbeat_fifteen_seconds_and_no_event_shape():
    clock = FrozenClock(AT + timedelta(seconds=14, milliseconds=999))
    state = HeartbeatState(AT)
    assert heartbeat_tick(state, clock=clock).comment is None
    clock.advance(timedelta(milliseconds=1))
    result = heartbeat_tick(state, clock=clock)
    assert result.comment == ": ping\n\n"
    assert "id:" not in result.comment and "data:" not in result.comment


def test_reset_and_old_sequence_are_idempotent_and_not_append():
    first = make_event(run_id="run1", seq=1, ts=AT, type="text_delta", payload={"text": "草稿"})
    reset = make_event(run_id="run1", seq=4, ts=AT, type="text_reset", payload={"text": "修订", "reason": "revised"})
    state = reduce_event(TextProjection(SCOPE), first, scope=SCOPE)
    state = reduce_event(state, reset, scope=SCOPE)
    assert state.text == "修订"
    assert reduce_event(state, first, scope=SCOPE) == state
    assert reduce_event(state, reset, scope=SCOPE) == state
    changed = make_event(run_id="run1", seq=4, ts=AT, type="text_reset", payload={"text": "冲突", "reason": "revised"})
    with pytest.raises(StreamStateError, match="同序号"):
        reduce_event(state, changed, scope=SCOPE)


def test_retention_clock_starts_at_commit_not_event_creation():
    commit = CommittedRun(SCOPE, AT + timedelta(days=3), 10, "message1")
    rows = (
        StoredEventMetadata(SCOPE, 1, "text_delta", AT, "0" * 64),
        StoredEventMetadata(SCOPE, 2, "text_reset", AT, "1" * 64),
        StoredEventMetadata(SCOPE, 10, "final", AT, "2" * 64),
    )
    assert not plan_delta_cleanup(commit, rows, clock=FrozenClock(AT + timedelta(days=3, hours=23))).eligible_refs
    due = plan_delta_cleanup(commit, rows, clock=FrozenClock(AT + timedelta(days=4)))
    assert [row.seq for row in due.eligible_refs] == [1]
    assert rows[0].type == "text_delta"


def test_foreign_cleanup_row_is_rejected_instead_of_deleted():
    commit = CommittedRun(SCOPE, AT, 10, "message1")
    foreign = StoredEventMetadata(RunScope("other", "run1"), 1, "text_delta", AT, "0" * 64)
    with pytest.raises(StreamStateError, match="其他运行"):
        plan_delta_cleanup(commit, (foreign,), clock=FrozenClock(AT + timedelta(days=1)))

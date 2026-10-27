"""Clocked batching, text revision, heartbeat and retention behavioral oracle."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest

from mingjing_core.streaming.cleanup import (
    CommittedRun,
    StoredEventMetadata,
    plan_delta_cleanup,
)
from mingjing_core.streaming.coalescer import (
    DeltaBuffer,
    feed_delta,
    flush_delta,
    poll_delta,
    replace_text,
)
from mingjing_core.streaming.event_models import EventDraft, RunScope, make_event
from mingjing_core.streaming.heartbeat import HeartbeatState, heartbeat_tick
from mingjing_core.streaming.memory_event_store import MemoryEventStore
from mingjing_core.streaming.stream_clock import StreamStateError
from mingjing_core.streaming.text_projection import TextProjection, reduce_event
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = RunScope("synthetic-owner", "synthetic-run")
SAMPLES = json.loads((Path(__file__).parent / "fixtures/event_samples_main_v1_mod.json").read_bytes())["samples"]


def event(kind, seq, payload=None, *, run_id=SCOPE.run_id):
    body = next(item["payload"] for item in SAMPLES if item["type"] == kind) if payload is None else payload
    return make_event(run_id=run_id, seq=seq, ts=AT, type=kind, payload=body)


def delta_text(drafts):
    assert all(draft.type == "text_delta" for draft in drafts)
    return "".join(draft.payload["text"] for draft in drafts)


def test_delta_flushes_at_40_characters_or_150_milliseconds_exactly():
    clock = FrozenClock(AT)
    first = feed_delta(DeltaBuffer(SCOPE), "甲" * 39, generation=0, clock=clock)
    assert not first.drafts and first.state.text == "甲" * 39
    clock.advance(timedelta(milliseconds=149))
    polled = poll_delta(first.state, clock=clock)
    assert not polled.drafts
    clock.advance(timedelta(milliseconds=1))
    elapsed = poll_delta(polled.state, clock=clock)
    assert delta_text(elapsed.drafts) == "甲" * 39 and not elapsed.state.text
    filled = feed_delta(DeltaBuffer(SCOPE), "乙" * 40, generation=0, clock=clock)
    assert delta_text(filled.drafts) == "乙" * 40 and not filled.state.text
    assert not flush_delta(filled.state, clock=clock).drafts


def test_reset_discards_unsent_draft_and_old_generation_cannot_write_after_it():
    clock = FrozenClock(AT)
    buffered = feed_delta(DeltaBuffer(SCOPE), "将被丢弃的旧草稿", generation=0, clock=clock)
    reset = replace_text(
        buffered.state,
        "新版完整答案",
        reason="revised",
        revision_id="new-revision",
        clock=clock,
    )
    assert len(reset.drafts) == 1 and reset.drafts[0].type == "text_reset"
    assert reset.drafts[0].payload["text"] == "新版完整答案"
    assert reset.state.text == "" and reset.state.generation == 1
    with pytest.raises(StreamStateError):
        feed_delta(reset.state, "迟到旧分片", generation=0, clock=clock)
    fresh = feed_delta(reset.state, "新补充", generation=1, clock=clock)
    assert delta_text(flush_delta(fresh.state, clock=clock).drafts) == "新补充"


@pytest.mark.parametrize("seed", range(30))
def test_random_utf8_chunks_preserve_exact_text_under_mixed_time_and_size_flushes(seed):
    rng, clock = Random(97013 + seed), FrozenClock(AT)
    buffer, expected, actual = DeltaBuffer(SCOPE), [], []
    for _ in range(40):
        chunk = "".join(rng.choice("中文🌙abc\n") for _ in range(rng.randint(1, 13)))
        expected.append(chunk)
        clock.advance(timedelta(milliseconds=rng.randrange(180)))
        outcome = feed_delta(buffer, chunk, generation=0, clock=clock)
        actual.append(delta_text(outcome.drafts))
        buffer = outcome.state
        if rng.randrange(3) == 0:
            outcome = poll_delta(buffer, clock=clock)
            actual.append(delta_text(outcome.drafts))
            buffer = outcome.state
    actual.append(delta_text(flush_delta(buffer, clock=clock).drafts))
    assert "".join(actual) == "".join(expected)


def test_projection_reset_replaces_text_stale_sequence_cannot_roll_it_back():
    state = reduce_event(TextProjection(SCOPE), event("text_delta", 2, {"text": "旧草稿"}), scope=SCOPE)
    revision = event(
        "text_reset",
        9,
        {"text": "修订全文", "reason": "revised", "revision_id": "opaque-id"},
    )
    state = reduce_event(state, revision, scope=SCOPE)
    assert state.text == "修订全文" and state.revision_id == "opaque-id"
    assert (
        reduce_event(
            state,
            event("text_reset", 3, {"text": "迟到旧版", "reason": "resumed"}),
            scope=SCOPE,
        )
        == state
    )
    assert reduce_event(state, revision, scope=SCOPE) == state
    state = reduce_event(state, event("text_delta", 12, {"text": "补充"}), scope=SCOPE)
    assert state.text == "修订全文补充"


def test_same_sequence_with_different_content_and_foreign_scope_are_rejected():
    state = reduce_event(TextProjection(SCOPE), event("text_delta", 5, {"text": "合成文本"}), scope=SCOPE)
    with pytest.raises(StreamStateError):
        reduce_event(state, event("text_delta", 5, {"text": "篡改文本"}), scope=SCOPE)
    with pytest.raises(StreamStateError):
        reduce_event(state, event("text_delta", 6), scope=RunScope("another", SCOPE.run_id))
    with pytest.raises(StreamStateError):
        reduce_event(state, event("text_delta", 6, run_id="foreign-run"), scope=SCOPE)


def test_final_envelope_is_authoritative_and_stops_future_generation():
    state = reduce_event(TextProjection(SCOPE), event("text_delta", 1, {"text": "过时初稿"}), scope=SCOPE)
    state = reduce_event(state, event("final", 9), scope=SCOPE)
    assert state.terminal and state.text == "合成最终答复。"
    with pytest.raises(StreamStateError):
        reduce_event(state, event("text_delta", 10), scope=SCOPE)
    assert reduce_event(state, event("text_delta", 1), scope=SCOPE) == state


def test_question_ends_generation_but_allows_a_final_envelope():
    state = reduce_event(TextProjection(SCOPE), event("ask_user", 1), scope=SCOPE)
    assert state.waiting_user
    for kind in ("text_delta", "text_reset", "ask_user", "tool_call", "tool_result"):
        with pytest.raises(StreamStateError):
            reduce_event(state, event(kind, 2), scope=SCOPE)
    assert reduce_event(state, event("final", 3), scope=SCOPE).terminal


def test_15_second_heartbeat_is_comment_only_and_does_not_consume_a_sequence():
    clock = FrozenClock(AT)
    store = MemoryEventStore(clock=clock)
    first = store.append(SCOPE, EventDraft("text_delta", {"text": "前"}), operation_id="first")
    state = HeartbeatState(AT)
    clock.advance(timedelta(milliseconds=14999))
    tick = heartbeat_tick(state, clock=clock)
    assert tick.comment is None
    clock.advance(timedelta(milliseconds=1))
    tick = heartbeat_tick(tick.state, clock=clock)
    assert tick.comment == ": ping\n\n"
    assert heartbeat_tick(tick.state, clock=clock).comment is None
    second = store.append(SCOPE, EventDraft("text_delta", {"text": "后"}), operation_id="second")
    assert second.event.seq == first.event.seq + 1


@pytest.mark.parametrize("component", ["buffer", "heartbeat"])
def test_clock_regression_is_not_silently_accepted(component):
    clock = FrozenClock(AT)
    if component == "buffer":
        state = feed_delta(DeltaBuffer(SCOPE), "文本", generation=0, clock=clock).state
    else:
        state = HeartbeatState(AT)
    clock.advance(timedelta(seconds=-1))
    with pytest.raises(StreamStateError):
        poll_delta(state, clock=clock) if component == "buffer" else heartbeat_tick(state, clock=clock)


def retention_rows():
    return tuple(
        StoredEventMetadata(SCOPE, seq, kind, created, str(seq) * 64)
        for seq, kind, created in (
            (1, "text_delta", AT - timedelta(days=5)),
            (2, "text_reset", AT),
            (3, "final", AT),
            (4, "text_delta", AT + timedelta(seconds=1)),
        )
    )


@pytest.mark.parametrize("offset,ready", [(-1, False), (0, True), (1, True)])
def test_cleanup_is_from_commit_plus_24h_and_only_removes_pre_final_deltas(offset, ready):
    committed = CommittedRun(SCOPE, AT, 3, "assistant-msg", revision=7)
    rows = retention_rows()
    clock = FrozenClock(AT + timedelta(hours=24, microseconds=offset))
    plan = plan_delta_cleanup(committed, rows, clock=clock)
    assert plan.ready == ready and plan.due_after == AT + timedelta(hours=24)
    assert [row.seq for row in plan.eligible_refs] == ([1] if ready else [])
    assert plan.expected_commit_revision == 7 and plan.final_seq == 3
    assert plan.message_id == "assistant-msg"
    assert rows == retention_rows()
    assert plan_delta_cleanup(committed, rows, clock=clock) == plan


def test_cleanup_rejects_cross_owner_run_and_conflicting_metadata():
    committed = CommittedRun(SCOPE, AT, 3, "assistant-msg")
    clock = FrozenClock(AT + timedelta(days=1))
    for foreign in (
        RunScope("foreign", SCOPE.run_id),
        RunScope(SCOPE.owner_id, "foreign"),
    ):
        row = replace(retention_rows()[0], scope=foreign)
        with pytest.raises(StreamStateError):
            plan_delta_cleanup(committed, (row,), clock=clock)
    with pytest.raises(StreamStateError):
        plan_delta_cleanup(committed, (retention_rows()[0],) * 2, clock=clock)


def test_real_store_metadata_can_feed_cleanup_without_private_text_or_manual_field_mapping():
    clock, store = FrozenClock(AT), MemoryEventStore(clock=FrozenClock(AT))
    first = store.append(
        SCOPE,
        EventDraft("text_delta", {"text": "合成私密文本标记"}),
        operation_id="delta",
    )
    final = store.append(
        SCOPE,
        EventDraft("final", next(s["payload"] for s in SAMPLES if s["type"] == "final")),
        operation_id="final",
    )
    metadata = store.metadata(SCOPE)
    assert "合成私密文本标记" not in repr(metadata)
    clock.advance(timedelta(days=1))
    committed = CommittedRun(SCOPE, AT, final.event.seq, "assistant-msg")
    plan = plan_delta_cleanup(committed, metadata, clock=clock)
    assert [row.seq for row in plan.eligible_refs] == [first.event.seq]

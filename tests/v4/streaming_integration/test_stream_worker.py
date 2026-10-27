"""Pure clock boundaries and actor stop/ack behavior are distinct from PG latency."""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from mingjing_core.application.run_event_stream import ModelDeltaStream
from mingjing_core.application.run_event_stream_worker import StreamCommand, StreamWorker
from mingjing_core.application.streaming_kernel import load_kernel
from mingjing_core.application.streaming_scope import HostStreamScope
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import FrozenClock


class BlockingState:
    def __init__(self) -> None:
        self.entered, self.release = threading.Event(), threading.Event()

    def begin(self, *args: Any, **kwargs: Any) -> dict:
        return {"generation": 1}

    def commit(self, *args: Any, **kwargs: Any) -> tuple[dict, list]:
        self.entered.set()
        assert self.release.wait(2), "test must release its synthetic blocked effect"
        return {"generation": 1}, []


def actor(state: BlockingState, ack_seconds: float = 0.2) -> StreamWorker:
    return StreamWorker(
        state,
        SimpleNamespace(),
        load_kernel(),
        HostStreamScope("s", "owner", "self", "life:self", "run").kernel_scope(),
        FrozenClock(datetime(2026, 10, 21, tzinfo=UTC)),
        lambda events: None,
        threading.Event(),
        ack_seconds=ack_seconds,
    )


def test_original_clock_boundary_is_149_then_150_ms() -> None:
    kernel = load_kernel()
    clock = FrozenClock(datetime(2026, 10, 21, tzinfo=UTC))
    scope = HostStreamScope("s", "owner", "self", "life:self", "run").kernel_scope()
    result = kernel.feed_delta(kernel.DeltaBuffer(scope), "合成短片", generation=0, clock=clock)
    clock.advance(timedelta(milliseconds=149))
    first = kernel.poll_delta(result.state, clock=clock)
    assert first.drafts == () and first.state.text == "合成短片"
    clock.advance(timedelta(milliseconds=1))
    second = kernel.poll_delta(first.state, clock=clock)
    assert [dict(item.payload) for item in second.drafts] == [{"text": "合成短片"}]


def test_stop_never_joins_or_waits_for_inflight_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    state = BlockingState()
    worker = actor(state)
    worker.start()
    command = StreamCommand("text", "合成片")
    worker.commands.put_nowait(command)
    assert state.entered.wait(1)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("stop must never call join")

    monkeypatch.setattr(worker.thread, "join", forbidden)
    started = time.monotonic()
    worker.stop()
    assert time.monotonic() - started < 0.1 and not worker.done.is_set()
    state.release.set()
    assert worker.done.wait(1)
    assert worker.buffer is None and worker.metadata is None


def test_normal_finish_ack_timeout_cancels_without_waiting_for_commit() -> None:
    state = BlockingState()
    worker = actor(state, ack_seconds=0.05)
    worker.start()
    started = time.monotonic()
    with pytest.raises(EvidenceError, match="本轮已停止"):
        worker.submit("finish")
    assert state.entered.is_set() and time.monotonic() - started < 0.3
    assert worker.cancel_event.is_set() and not worker.done.is_set()
    state.release.set()
    assert worker.done.wait(1)


def test_actor_queue_is_bounded_and_overflow_stops_the_run() -> None:
    worker = actor(BlockingState())
    assert worker.commands.maxsize == 2
    worker.commands.put_nowait(StreamCommand("text", "甲"))
    worker.commands.put_nowait(StreamCommand("text", "乙"))
    with pytest.raises(EvidenceError):
        worker.submit("text", "丙")
    assert worker.stopped.is_set() and worker.cancel_event.is_set()


class DelayedMarker:
    def __init__(self) -> None:
        self.marker, self.entered, self.release = threading.Event(), threading.Event(), threading.Event()

    def set(self) -> None:
        self.entered.set()
        assert self.release.wait(1)
        self.marker.set()

    def clear(self) -> None:
        self.marker.clear()

    def is_set(self) -> bool:
        return self.marker.is_set()


def facade(worker: StreamWorker) -> ModelDeltaStream:
    value = ModelDeltaStream.__new__(ModelDeltaStream)
    value.step, value.worker = worker.step, worker
    return value


def test_stop_before_a_late_inflight_marker_prevents_any_new_effect() -> None:
    state, marker = BlockingState(), DelayedMarker()
    worker = actor(state)
    worker.start()
    worker.write_inflight = marker
    worker.commands.put_nowait(StreamCommand("text", "合成片"))
    assert marker.entered.wait(1) and not marker.is_set()
    started = time.monotonic()
    facade(worker).finish(worker.step, succeeded=False)
    assert time.monotonic() - started < 0.1
    marker.release.set()
    assert worker.done.wait(1)
    assert not state.entered.is_set() and worker.failure is None


def test_callback_completion_is_inside_inflight_gate_before_any_final() -> None:
    state, entered, release = BlockingState(), threading.Event(), threading.Event()
    state.release.set()
    worker = actor(state)
    worker.start()

    def callback(events: list) -> None:
        entered.set()
        assert release.wait(1)

    worker.deliver = callback
    worker.commands.put_nowait(StreamCommand("text", "合成片"))
    assert entered.wait(1) and worker.write_inflight.is_set()
    started = time.monotonic()
    with pytest.raises(EvidenceError, match="结果尚未确认"):
        facade(worker).finish(worker.step, succeeded=False)
    assert time.monotonic() - started < 0.1
    release.set()
    assert worker.done.wait(1) and not worker.write_inflight.is_set()

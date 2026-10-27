"""One actor owns the pure buffer; stopped callers never join its database work."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from mingjing_core.agent.journal import JournalStep
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import Clock

from .run_event_stream_state import StreamState


@dataclass
class StreamCommand:
    kind: str
    text: str = field(default="", repr=False)
    acknowledged: threading.Event = field(default_factory=threading.Event, repr=False)


class StreamAborted(Exception):
    """A locally stopped actor must not begin a later write."""


class StreamWorker:
    def __init__(
        self,
        state: StreamState,
        step: JournalStep,
        kernel: Any,
        scope: Any,
        clock: Clock,
        deliver: Callable[[list[dict[str, Any]]], None],
        cancel_event: threading.Event,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        ack_seconds: float = 0.75,
    ) -> None:
        self.state, self.step, self.kernel, self.scope, self.clock = state, step, kernel, scope, clock
        self.deliver, self.cancel_event = deliver, cancel_event
        self.monotonic, self.ack_seconds = monotonic, ack_seconds
        self.commands: queue.Queue[StreamCommand] = queue.Queue(maxsize=2)
        self.stopped, self.done, self.ready = threading.Event(), threading.Event(), threading.Event()
        self.write_inflight = threading.Event()
        self.failure: EvidenceError | None = None
        self.metadata: dict[str, Any] | None = None
        self.buffer: Any = None
        self.deadline: float | None = None
        self.thread = threading.Thread(target=self._run, name="agent-stream-buffer", daemon=True)

    def start(self) -> None:
        self.thread.start()
        self._await(self.ready)

    def _fail(self) -> None:
        self.failure = EvidenceError("流式刷新未安全完成，本轮已停止")
        self.cancel_event.set()
        self.stopped.set()

    def _check(self) -> None:
        if self.failure is not None:
            raise self.failure
        if self.stopped.is_set() or self.cancel_event.is_set():
            raise EvidenceError("流式刷新已经停止")

    def _await(self, acknowledged: threading.Event) -> None:
        deadline = self.monotonic() + self.ack_seconds
        while not acknowledged.wait(min(0.01, max(0, deadline - self.monotonic()))):
            self._check()
            if self.monotonic() >= deadline:
                self._fail()
                self.stop()
                raise self.failure  # type: ignore[misc]
        self._check()

    def submit(self, kind: str, text: str = "") -> None:
        self._check()
        command = StreamCommand(kind, text)
        try:
            self.commands.put_nowait(command)
        except queue.Full:
            self._fail()
            self.stop()
            raise self.failure from None  # type: ignore[misc]
        self._await(command.acknowledged)

    def stop(self) -> None:
        # No worker/buffer/owner lock, acknowledgment wait or join is permitted here.
        self.stopped.set()
        while True:
            try:
                pending = self.commands.get_nowait()
                pending.text = ""
                pending.acknowledged.set()
            except queue.Empty:
                break
        with suppress(queue.Full):
            self.commands.put_nowait(StreamCommand("stop"))

    def _schedule(self) -> None:
        if not self.buffer.text:
            self.deadline = None
            return
        remaining = (self.buffer.opened_at + timedelta(milliseconds=150) - self.clock.now()).total_seconds()
        self.deadline = self.monotonic() + max(0.001, remaining)

    @contextmanager
    def _writing(self) -> Iterator[None]:
        self.write_inflight.set()
        try:
            if self.stopped.is_set():
                raise StreamAborted()
            self._check()
            yield
        except StreamAborted:
            raise
        except BaseException:
            # Failure precedes clearing the marker, so a failed finish cannot
            # mistake a not-yet-acknowledged write for a known safe boundary.
            self._fail()
            raise
        finally:
            self.write_inflight.clear()

    def _apply(self, result: Any, chunk: str = "", *, closed: bool = False) -> None:
        with self._writing():
            assert self.metadata is not None
            metadata, events = self.state.commit(
                self.step, self.metadata, chunk, result.drafts, closed=closed, stopped=self.stopped
            )
            self.metadata, self.buffer = metadata, result.state
            self._schedule()
            if not self.stopped.is_set() and not self.cancel_event.is_set():
                self.deliver(events)

    def _handle(self, command: StreamCommand) -> bool:
        if command.kind == "text":
            result = self.kernel.feed_delta(
                self.buffer, command.text, generation=self.metadata["generation"], clock=self.clock
            )
            self._apply(result, command.text)
            return False
        if command.kind == "finish":
            self._apply(self.kernel.flush_delta(self.buffer, clock=self.clock), closed=True)
            return True
        raise EvidenceError("流式刷新命令无效")

    def _consume(self) -> None:
        while not self.stopped.is_set():
            timeout = None if self.deadline is None else max(0, self.deadline - self.monotonic())
            try:
                command = self.commands.get(timeout=timeout)
            except queue.Empty:
                self._apply(self.kernel.poll_delta(self.buffer, clock=self.clock))
                continue
            if command.kind == "stop":
                return
            try:
                if self._handle(command):
                    return
            except StreamAborted:
                raise
            except BaseException:
                self._fail()
                raise
            finally:
                command.text = ""
                command.acknowledged.set()

    def _run(self) -> None:
        try:
            with self._writing():
                self.metadata = self.state.begin(self.step, stopped=self.stopped)
            self.buffer = self.kernel.DeltaBuffer(self.scope, generation=self.metadata["generation"])
            self.ready.set()
            self._consume()
        except StreamAborted:
            pass
        except BaseException:
            self._fail()
        finally:
            self.ready.set()
            self.buffer, self.metadata, self.deadline = None, None, None
            self.done.set()

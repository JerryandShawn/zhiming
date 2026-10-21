"""Real Runtime consumer delegates its only buffer to an independently waking actor."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from mingjing_core.agent.journal import JournalStep
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_thread_scope import thread_id
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock

from .run_event_stream_state import StreamState
from .run_event_stream_worker import StreamWorker
from .streaming_kernel import load_kernel
from .streaming_scope import HostStreamScope


class ModelDeltaStream:
    def __init__(
        self,
        repo: PostgresRepository,
        run: dict[str, Any],
        ledger: RequestLedger,
        callback: Callable[[dict[str, Any]], None] | None,
        *,
        cancel_event: threading.Event,
        clock: Clock | None = None,
    ) -> None:
        self.kernel, self.clock = load_kernel(), clock or get_clock()
        self.scope = HostStreamScope(repo.schema, run["owner"], run["subject"], thread_id(run), run["id"])
        if not isinstance(cancel_event, threading.Event):
            raise EvidenceError("流式刷新需要受信取消信号")
        self.state, self.callback, self.cancel_event = StreamState(repo, run, ledger), callback, cancel_event
        self.step: JournalStep | None = None
        self.worker: StreamWorker | None = None

    def begin(self, step: JournalStep) -> None:
        if self.step is not None:
            raise EvidenceError("流式模型步骤不能重入")
        worker = StreamWorker(
            self.state, step, self.kernel, self.scope.kernel_scope(), self.clock, self._deliver, self.cancel_event
        )
        try:
            worker.start()
        except BaseException:
            worker.stop()
            raise
        self.step, self.worker = step, worker

    def _deliver(self, events: list[dict[str, Any]]) -> None:
        if self.callback is None:
            return
        for event in events:
            try:
                self.callback(event)
            except Exception:
                # A disconnected subscriber cannot undo the actual committed event.
                continue

    def push(self, text: str) -> None:
        if self.step is None or self.worker is None:
            raise EvidenceError("流式正文缺少真实模型步骤")
        if not isinstance(text, str) or not text:
            raise EvidenceError("流式正文片段无效")
        self.worker.submit("text", text)

    def finish(self, step: JournalStep, *, succeeded: bool) -> None:
        if self.step != step or self.worker is None:
            raise EvidenceError("流式结束步骤与当前步骤不符")
        try:
            if succeeded:
                self.worker.submit("finish")
            else:
                self.worker.stop()
                if self.worker.failure is not None:
                    # A provider error must not hide an actor write failure and
                    # accidentally publish its partial draft.
                    raise self.worker.failure
                if self.worker.write_inflight.is_set():
                    raise EvidenceError("流式写入结果尚未确认，本轮已停止")
        finally:
            # Failure stops scheduling without joining or waiting for a blocked write.
            self.worker.stop()
            self.step, self.worker = None, None

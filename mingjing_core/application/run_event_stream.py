"""Real Runtime consumer of the source-pinned pure coalescer; no independent timer yet."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mingjing_core.agent.journal import JournalStep
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_thread_scope import thread_id
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock

from .run_event_stream_state import StreamState
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
        clock: Clock | None = None,
    ) -> None:
        self.kernel, self.clock = load_kernel(), clock or get_clock()
        self.scope = HostStreamScope(repo.schema, run["owner"], run["subject"], thread_id(run), run["id"])
        self.state, self.callback = StreamState(repo, run, ledger), callback
        self.step: JournalStep | None = None
        self.metadata: dict[str, Any] | None = None
        self.buffer: Any = None

    def begin(self, step: JournalStep) -> None:
        if self.step is not None:
            raise EvidenceError("流式模型步骤不能重入")
        scope = self.scope.kernel_scope()
        metadata = self.state.begin(step)
        self.step, self.metadata = step, metadata
        self.buffer = self.kernel.DeltaBuffer(scope, generation=metadata["generation"])

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
        if self.step is None or self.metadata is None:
            raise EvidenceError("流式正文缺少真实模型步骤")
        if not isinstance(text, str) or not text:
            raise EvidenceError("流式正文片段无效")
        result = self.kernel.feed_delta(
            self.buffer,
            text,
            generation=self.metadata["generation"],
            clock=self.clock,
        )
        metadata, events = self.state.commit(self.step, self.metadata, text, result.drafts)
        self.metadata, self.buffer = metadata, result.state
        self._deliver(events)

    def finish(self, step: JournalStep, *, succeeded: bool) -> None:
        if self.step != step or self.metadata is None:
            raise EvidenceError("流式结束步骤与当前步骤不符")
        try:
            if succeeded:
                result = self.kernel.flush_delta(self.buffer, clock=self.clock)
                self.metadata, events = self.state.commit(step, self.metadata, "", result.drafts, closed=True)
                self._deliver(events)
            # Failure discards memory without PG cleanup or a blocking join. Persistent
            # unfinished state refuses regeneration until the audited reset bridge exists.
        finally:
            self.step, self.metadata, self.buffer = None, None, None

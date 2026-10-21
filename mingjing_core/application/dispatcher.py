"""Bounded two-lane workers execute a claimed RuntimePort outside PG transactions."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from typing import Any

from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_claims import DispatcherClaims
from mingjing_core.application.dispatcher_notifications import (
    NotificationBridge,
    RunSignals,
)
from mingjing_core.application.dispatcher_service import DispatcherServiceProxy
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict
from mingjing_core.models.quota_runtime import current_scope


class AgentDispatcher:
    def __init__(self, service: Any, *, signals: RunSignals | None = None, runtime: Any = None) -> None:
        self.service, self.repo, self.runtime = service, service.repo, runtime or service.runtime
        self.claims = DispatcherClaims(self.repo)
        self.signals = signals or RunSignals()
        self.cancellation = DispatcherCancellation(self.repo, self.signals)
        self.wake, self.stop = threading.Event(), threading.Event()
        self.bridge = NotificationBridge(self.repo, self.wake.set, self.signals)
        self.capacity = self.repo.max_running if self.repo.max_running is not None else 3
        self.executor = ThreadPoolExecutor(max_workers=self.capacity, thread_name_prefix="agent-dispatch")
        self.active: dict[str, Future[Any]] = {}
        self.guard = threading.RLock()
        self.thread: threading.Thread | None = None
        self.failures = 0

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        if current_scope().lane in {"eval", "probe"}:
            raise EvidenceError("短期人工批次不能绑定常驻调度器，请使用受信单批入口")
        self.stop.clear()
        self.bridge.start()
        self.thread = threading.Thread(target=self._serve, name="agent-dispatcher", daemon=True)
        self.thread.start()

    def _serve(self) -> None:
        while not self.stop.is_set():
            self.wake.clear()
            try:
                self.tick()
            except Exception:
                # Operational counts contain no source or transport error bodies.
                self.failures += 1
            self.wake.wait(2)

    def tick(self) -> int:
        with self.guard:
            self.claims.recover()
            self.active = {key: future for key, future in self.active.items() if not future.done()}
            added = 0
            for lane in ("interactive", "background"):
                while len(self.active) < self.capacity:
                    run = self.claims.claim(lane)
                    if run is None:
                        break
                    self.signals.event(run["owner"], run["id"])
                    future = self.executor.submit(copy_context().run, self._execute, run)
                    self.active[run["id"]] = future
                    future.add_done_callback(lambda _: self.wake.set())
                    added += 1
            return added

    def _execute(self, run: dict[str, Any]) -> dict[str, Any] | None:
        service = DispatcherServiceProxy(self.service, run)
        try:
            return self.runtime.execute(service, run["owner"], run["id"], run["lease_token"])
        except Exception as error:
            self.failures += 1
            run = service.run
            current = self.repo.fetch_run(run["owner"], run["id"])
            # A replacement worker/clean epoch owns a different lease. Never
            # mark it failed using a stale worker's completion.
            if current["status"] != "running" or current["lease_token"] != run["lease_token"]:
                return None
            try:
                if current["cancel_requested_at"]:
                    return self.cancellation.finish(run)
                status = "stale" if isinstance(error, RevisionConflict) else "failed"
                return self.repo.fail_run(
                    run["owner"], run["id"], "本轮尚未完成，请恢复原请求", run["lease_token"], status=status
                )
            except CoreError:
                return None
        finally:
            self.signals.release(run["owner"], run["id"])

    def close(self, *, wait: bool = True) -> None:
        self.stop.set()
        self.wake.set()
        self.bridge.close()
        if self.thread:
            self.thread.join(timeout=3)
        self.executor.shutdown(wait=wait, cancel_futures=True)

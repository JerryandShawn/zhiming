"""LISTEN is a wakeup optimization; the queue and cancellation flags remain PG authority."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

import psycopg
from psycopg import sql

from mingjing_core.agent.loop_policy import RunControl
from mingjing_core.repositories.postgres import PostgresRepository


class RunSignals:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], threading.Event] = {}
        self._lock = threading.Lock()

    def event(self, owner: str, ident: str) -> threading.Event:
        with self._lock:
            return self._events.setdefault((owner, ident), threading.Event())

    def cancel(self, ident: str) -> None:
        with self._lock:
            for (_, run_id), event in self._events.items():
                if ident == run_id:
                    event.set()

    def release(self, owner: str, ident: str) -> None:
        with self._lock:
            self._events.pop((owner, ident), None)

    def controls(self, repo: Any, run: dict[str, Any], policy: Any, **kwargs: Any) -> RunControl:
        return RunControl(repo, run, policy, cancel_event=self.event(run["owner"], run["id"]), **kwargs)


class NotificationBridge:
    def __init__(self, repo: PostgresRepository, wake: Callable[[], None], signals: RunSignals) -> None:
        self.repo, self.wake, self.signals = repo, wake, signals
        self.stop, self.ready = threading.Event(), threading.Event()
        self.thread: threading.Thread | None = None
        self.failures = 0

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._listen, name="agent-pg-listener", daemon=True)
        self.thread.start()

    def _listen(self) -> None:
        while not self.stop.is_set():
            try:
                with psycopg.connect(self.repo.dsn, autocommit=True) as connection:
                    connection.execute("LISTEN mj_run_queued")
                    connection.execute("LISTEN mj_run_cancel")
                    self.ready.set()
                    while not self.stop.is_set():
                        for notice in connection.notifies(timeout=0.25, stop_after=1):
                            self._notice(notice.channel, notice.payload)
            except psycopg.Error:
                self.failures += 1
                self.ready.clear()
                self.stop.wait(1)

    def _notice(self, channel: str, payload: str) -> None:
        try:
            value = json.loads(payload)
            if set(value) != {"schema", "run_id"} or value["schema"] != self.repo.schema:
                return
            if not isinstance(value["run_id"], str) or not 1 <= len(value["run_id"]) <= 200:
                return
        except (ValueError, TypeError):
            return
        if channel == "mj_run_cancel":
            with self.repo.transaction() as connection:
                row = connection.execute(
                    sql.SQL("SELECT cancel_requested_at FROM {} WHERE id=%s").format(self.repo.table("core_runs")),
                    (value["run_id"],),
                ).fetchone()
            if row and row["cancel_requested_at"] is not None:
                self.signals.cancel(value["run_id"])
        self.wake()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)

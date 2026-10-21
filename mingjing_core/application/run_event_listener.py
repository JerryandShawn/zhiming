"""A dedicated committed-notification connection; never queries or publishes payloads."""

from __future__ import annotations

import threading

import psycopg

from mingjing_core.domain.contracts import EvidenceError

from .run_event_hub import RunEventHub

APPLICATION_NAME = "mingjing-event-hints-v1"


def parse_notice(payload: str) -> tuple[str, int] | None:
    if not isinstance(payload, str) or not 3 <= len(payload) <= 220:
        return None
    ident, separator, raw = payload.rpartition(":")
    if (
        not separator
        or not 1 <= len(ident) <= 200
        or not raw.isascii()
        or not raw.isdecimal()
        or len(raw) > 19
    ):
        return None
    seq = int(raw)
    if not 0 < seq < 2**63 or raw != str(seq):
        return None
    return ident, seq


class EventListener:
    def __init__(self, dsn: str, hub: RunEventHub) -> None:
        self._dsn, self.hub = dsn, hub
        self.stop, self.ready = threading.Event(), threading.Event()
        self._guard = threading.Lock()
        self._connection: psycopg.Connection | None = None
        self.thread: threading.Thread | None = None
        self.failures, self.notifications = 0, 0
        self.last_code = "EVENT_LISTEN_NOT_STARTED"

    def start(self) -> None:
        if self.thread is not None:
            raise EvidenceError("事件监听服务不能重复启动")
        self.thread = threading.Thread(
            target=self._run, name="run-event-listener", daemon=True
        )
        self.thread.start()

    def _run(self) -> None:
        while not self.stop.is_set():
            try:
                self._connected()
            except psycopg.Error:
                if not self.stop.is_set():
                    self.failures = min(self.failures + 1, 2**63 - 1)
                    self.last_code = "EVENT_LISTEN_UNAVAILABLE"
            except Exception:
                self.last_code = "EVENT_LISTEN_FAILED"
                return
            finally:
                self.ready.clear()
            if not self.stop.is_set():
                self.stop.wait(min(0.1 * 2 ** min(self.failures, 6), 5.0))

    def _connected(self) -> None:
        with psycopg.connect(
            self._dsn,
            autocommit=True,
            connect_timeout=2,
            application_name=APPLICATION_NAME,
        ) as connection:
            with self._guard:
                self._connection = connection
            try:
                connection.execute("LISTEN mj_run")
                self.last_code = "EVENT_LISTEN_READY"
                self.ready.set()
                while not self.stop.is_set():
                    for notice in connection.notifies(timeout=0.1, stop_after=64):
                        if self.stop.is_set():
                            return
                        value = (
                            parse_notice(notice.payload)
                            if notice.channel == "mj_run"
                            else None
                        )
                        if value is not None:
                            self.notifications = min(self.notifications + 1, 2**63 - 1)
                            self.hub.publish(*value)
            finally:
                with self._guard:
                    if self._connection is connection:
                        self._connection = None

    def close(self) -> None:
        self.stop.set()
        with self._guard:
            connection = self._connection
        if connection is not None:
            connection.close()
        if self.thread is not None:
            self.thread.join(timeout=3)
            if self.thread.is_alive():
                raise EvidenceError("事件监听服务尚未完成关闭")
        self.ready.clear()
        self.last_code = "EVENT_LISTEN_CLOSED"

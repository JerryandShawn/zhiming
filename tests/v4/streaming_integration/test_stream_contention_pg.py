"""A genuine short owner read releases only after a genuine busy PG probe."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from mingjing_core.domain.contracts import LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.streaming_transaction import streaming_transaction
from mingjing_core.timekit.clock import SystemClock, get_clock, set_clock
from tests.v4.streaming_integration.stream_timer_support import QuietPort, launch, read_deltas


class ObservedCursor:
    def __init__(self, raw: Any, handshake: ShortRead) -> None:
        self.raw, self.handshake = raw, handshake

    def fetchone(self) -> Any:
        result = self.raw.fetchone()
        if result["acquired"] is False:
            self.handshake.busy_count += 1
            self.handshake.busy.set()
            if self.handshake.stop_on_busy is not None:
                self.handshake.stop_on_busy.set()
        return result


class ObservedConnection:
    def __init__(self, raw: Any, handshake: ShortRead) -> None:
        self.raw, self.handshake = raw, handshake

    def __getattr__(self, name: str) -> Any:
        return getattr(self.raw, name)

    def execute(self, query: Any, *args: Any, **kwargs: Any) -> Any:
        cursor = self.raw.execute(query, *args, **kwargs)
        if isinstance(query, str) and query.startswith("SELECT pg_try_advisory_xact_lock"):
            return ObservedCursor(cursor, self.handshake)
        return cursor


class ShortRead:
    def __init__(
        self, repo: PostgresRepository, *, timer: bool = False, stopped: threading.Event | None = None
    ) -> None:
        self.repo, self.timer, self.stop_on_busy = repo, timer, stopped
        self.requested, self.held, self.busy, self.done = (threading.Event() for _ in range(4))
        self.errors: list[str] = []
        self.busy_count, self.actor_calls = 0, 0
        self.main_ident = threading.get_ident()
        self.original = repo.pool.connection
        self.reader = threading.Thread(target=self._read, daemon=True)

    def _read(self) -> None:
        try:
            assert self.requested.wait(1)
            with self.repo.transaction("alice"):
                assert self.repo.assert_scope("alice")["id"] == "self"
                self.held.set()
                assert self.busy.wait(1), "actual writer must observe a busy lock before the reader releases"
        except BaseException as error:
            self.errors.append(type(error).__name__)
        finally:
            self.done.set()

    @contextmanager
    def connection(self, *args: Any, **kwargs: Any) -> Iterator[Any]:
        actor = threading.current_thread().name == "agent-stream-buffer"
        observed = actor if self.timer else threading.get_ident() == self.main_ident
        with self.original(*args, **kwargs) as raw:
            if actor:
                self.actor_calls += 1
                if self.timer and self.actor_calls == 3:
                    self.requested.set()
                    assert self.held.wait(1)
            yield ObservedConnection(raw, self) if observed else raw

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(self.repo.pool, "connection", self.connection)
        self.reader.start()
        if not self.timer:
            self.requested.set()
            assert self.held.wait(1)

    def close(self) -> None:
        self.requested.set()
        self.busy.set()
        self.reader.join(1)
        assert not self.reader.is_alive() and not self.errors


def test_short_legitimate_owner_read_does_not_permanently_fail_writer(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    handshake = ShortRead(p2_repo)
    handshake.install(monkeypatch)
    try:
        with streaming_transaction(p2_repo, "alice"):
            assert p2_repo.assert_scope("alice")["id"] == "self"
        assert handshake.busy_count >= 1 and handshake.done.wait(1)
    finally:
        handshake.close()


def test_stop_after_first_real_busy_probe_prevents_a_retry_or_write(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    stopped = threading.Event()
    handshake = ShortRead(p2_repo, stopped=stopped)
    handshake.install(monkeypatch)
    try:
        with pytest.raises(LeaseConflict), streaming_transaction(p2_repo, "alice", stopped):
            pytest.fail("stopped writer must not enter its effect")
        assert handshake.busy_count == 1
    finally:
        handshake.close()


def test_real_timer_waits_for_a_short_owner_read_and_persists_without_regeneration(
    p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = get_clock()
    set_clock(SystemClock())
    handshake, port = ShortRead(p2_repo, timer=True), QuietPort()
    handshake.install(monkeypatch)
    thread = None
    try:
        run, thread, observed = launch(p2_repo, port)
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline and not read_deltas(p2_repo, run) and not port.cancelled.is_set():
            time.sleep(0.005)
        assert handshake.busy_count >= 1 and handshake.done.wait(1)
        assert read_deltas(p2_repo, run) == ["静默合成片"] and not port.cancelled.is_set()
        port.release.set()
        thread.join(1)
        assert not thread.is_alive() and observed["result"]["text"] == "静默合成片结束" and port.calls == 1
    finally:
        port.release.set()
        handshake.close()
        if thread is not None:
            thread.join(1)
        set_clock(previous)

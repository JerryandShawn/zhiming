"""Real PG and pure calendar synchronization; no application result is faked."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.models.port import ToolCall

from .test_loop_cycle_support import cycle_repo as source_fixture


@pytest.fixture
def parallel_repo(p2_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    yield from source_fixture.__wrapped__(p2_repo, monkeypatch)


def clocks(*days: int) -> list[ToolCall]:
    return [
        ToolCall(f"clock-{index}", "time_context", {"date": f"2026-10-{day:02d}"}) for index, day in enumerate(days)
    ]


def tool_rows(repo: Any, run: dict) -> list[dict]:
    with repo.transaction("alice") as connection:
        return connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner='alice' AND run_id=%s AND kind='tool' ORDER BY seq").format(
                repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchall()


class CalendarGate:
    def __init__(self, repo: Any, actual: Any) -> None:
        self.repo, self.actual = repo, actual
        self.started, self.release = threading.Event(), threading.Event()
        self.workers: list[threading.Thread] = []
        self.lock = threading.Lock()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        assert getattr(self.repo._local, "connection", None) is None, "pure computation still holds the PG owner lock"
        with self.lock:
            self.workers.append(threading.current_thread())
            if len(self.workers) == 2:
                self.started.set()
        assert self.release.wait(5), "test did not release pure computation"
        return self.actual(*args, **kwargs)

    def close(self) -> None:
        self.release.set()
        for worker in self.workers:
            worker.join(timeout=2)
            assert not worker.is_alive()

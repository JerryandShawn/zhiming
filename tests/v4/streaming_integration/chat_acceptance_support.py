"""Real socket fixtures use only an explicitly injected, bounded scripted model."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest
from psycopg import sql

from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.streaming_integration.event_http_support import isolate


class WaitingPort(ScriptedPort):
    def __init__(self) -> None:
        super().__init__([answer("合成异步答复")])
        self.started, self.release = threading.Event(), threading.Event()

    def stream(self, messages: Any, **kwargs: Any) -> Iterator[Any]:
        self.started.set()
        if not self.release.wait(8):
            raise AssertionError("bounded synthetic model was not released")
        yield from super().stream(messages, **kwargs)


@pytest.fixture(name="acceptance_repo")
def repository(p2_repo: Any, monkeypatch: Any) -> Any:
    isolate(monkeypatch)
    return p2_repo


def counts(repo: Any) -> tuple[int, ...]:
    with repo.transaction() as connection:
        return tuple(
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(repo.table(table))
            ).fetchone()["n"]
            for table in (
                "core_owners",
                "core_subjects",
                "core_entities",
                "core_runs",
                "core_operations",
            )
        )

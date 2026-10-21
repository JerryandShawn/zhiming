"""Real PG commit hints share one connection; all payloads stay in the reader."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from psycopg import sql

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.run_event_listener import APPLICATION_NAME
from mingjing_core.application.run_event_service import acquire_event_hints
from mingjing_core.repositories.postgres import PostgresRepository
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started


async def until(predicate: Any, timeout: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("bounded local event condition did not occur")
        await asyncio.sleep(0.01)


def listeners(repo: PostgresRepository) -> list[int]:
    with repo.transaction() as connection:
        return [
            row["pid"]
            for row in connection.execute(
                "SELECT pid FROM pg_stat_activity WHERE datname=current_database() "
                "AND usename=current_user AND application_name=%s",
                (APPLICATION_NAME,),
            )
        ]


def test_real_listener_is_one_connection_and_only_wakes_after_commit(p2_repo):
    repo, run = p2_repo, claimed(p2_repo)

    async def exercise():
        first, second = acquire_event_hints(repo), acquire_event_hints(repo)
        sub = first.subscribe(repo, run["owner"], run["id"])
        other = second.subscribe(repo, run["owner"], run["id"])
        try:
            await until(lambda: first.statistics()["listener_ready"])
            assert len(listeners(repo)) == 1
            with repo.transaction(run["owner"]):
                RuntimeEvents(repo, run, None).send("started", started(run))
                assert await sub.wait(0.05) is None
            assert await sub.wait(2) == await other.wait(2) == 1
            with repo.transaction(run["owner"]) as connection:
                assert (
                    connection.execute(
                        sql.SQL("SELECT seq FROM {} WHERE run_id=%s").format(
                            repo.table("core_run_events")
                        ),
                        (run["id"],),
                    ).fetchone()["seq"]
                    == 1
                )
            first.close()
            assert len(listeners(repo)) == 1
        finally:
            first.close()
            second.close()
        assert listeners(repo) == []

    asyncio.run(exercise())


def test_real_listener_rollback_has_no_hint_then_reconnects_after_own_socket_is_terminated(
    p2_repo,
):
    repo, run = p2_repo, claimed(p2_repo)

    async def exercise():
        hints = acquire_event_hints(repo)
        sub = hints.subscribe(repo, run["owner"], run["id"])
        try:
            await until(lambda: hints.statistics()["listener_ready"])
            try:
                with repo.transaction(run["owner"]):
                    RuntimeEvents(repo, run, None).send("started", started(run))
                    raise RuntimeError("synthetic rollback")
            except RuntimeError:
                pass
            assert await sub.wait(0.1) is None
            previous = listeners(repo)
            assert len(previous) == 1
            with repo.transaction() as connection:
                assert connection.execute(
                    "SELECT pg_terminate_backend(%s) AS ok", (previous[0],)
                ).fetchone()["ok"]
            await until(lambda: hints.statistics()["failures"] >= 1)
            await until(lambda: hints.statistics()["listener_ready"])
            assert len(listeners(repo)) == 1 and listeners(repo) != previous
            RuntimeEvents(repo, run, None).send("started", started(run))
            assert await sub.wait(2) == 1
            assert hints.statistics()["subscriptions"] == 1
        finally:
            hints.close()
        assert listeners(repo) == []

    asyncio.run(exercise())

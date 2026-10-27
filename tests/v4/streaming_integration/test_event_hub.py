"""Only integer hints are merged; paused event loops cannot accumulate callbacks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from mingjing_core.application.run_event_hub import RunEventHub
from mingjing_core.application.run_event_listener import parse_notice
from mingjing_core.application.run_event_service import acquire_event_hints
from mingjing_core.domain.contracts import EvidenceError


def test_slow_loop_merges_before_scheduling_and_does_not_cache_unknown_runs():
    loop, hub = asyncio.new_event_loop(), RunEventHub()
    scope = hub.open_scope(loop)
    first, second = (
        hub.subscribe(scope, "使用者", "run:one"),
        hub.subscribe(scope, "other", "run:one"),
    )
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks = [pool.submit(hub.publish, "run:one", seq) for seq in range(1, 3001)]
            for task in tasks:
                task.result()
        for seq in range(1, 3001):
            hub.publish("unknown-" + str(seq), seq)
        assert hub.statistics() == {
            "scopes": 1,
            "subscriptions": 2,
            "runs": 1,
            "pending_callbacks": 1,
            "queued_hints": 0,
        }
        loop.run_until_complete(asyncio.sleep(0))
        assert first.queue.qsize() == second.queue.qsize() == 1
        assert first.queue.get_nowait() == second.queue.get_nowait() == 3000
        hub.publish("run:one", 2**63 - 1)
        loop.run_until_complete(asyncio.sleep(0))
        assert first.queue.get_nowait() == 2**63 - 1
        hub.publish("run:one", 3)
        loop.run_until_complete(asyncio.sleep(0))
        assert first.queue.get_nowait() == 3
    finally:
        hub.close_scope(scope)
        loop.close()
    assert hub.statistics() == {
        "scopes": 0,
        "subscriptions": 0,
        "runs": 0,
        "pending_callbacks": 0,
        "queued_hints": 0,
    }


def test_subscription_churn_in_one_paused_app_still_has_one_callback():
    loop, hub = asyncio.new_event_loop(), RunEventHub(capacity=2, per_run=2)
    scope = hub.open_scope(loop)
    try:
        for seq in range(1, 2001):
            value = hub.subscribe(scope, "alice", "run")
            hub.publish("run", seq)
            value.close()
            value.close()
        assert hub.statistics()["pending_callbacks"] == 1
        assert hub.statistics()["subscriptions"] == hub.statistics()["runs"] == 0
        loop.run_until_complete(asyncio.sleep(0))
        assert hub.statistics()["pending_callbacks"] == 0
    finally:
        hub.close_scope(scope)
        loop.close()


def test_queue_merges_highest_without_losing_lower_future_hints_after_consumption():
    loop, hub = asyncio.new_event_loop(), RunEventHub()
    scope = hub.open_scope(loop)
    value = hub.subscribe(scope, "alice", "run")
    try:
        for seq in (100, 5, 90):
            hub.publish("run", seq)
            loop.run_until_complete(asyncio.sleep(0))
            assert value.queue.qsize() == 1
        assert loop.run_until_complete(value.wait(0.1)) == 100
        hub.publish("run", 6)
        assert loop.run_until_complete(value.wait(0.1)) == 6
        value.close()
        assert loop.run_until_complete(value.wait(0.1)) is None
        hub.publish("run", 7)
        loop.run_until_complete(asyncio.sleep(0))
        assert value.queue.empty()
    finally:
        hub.close_scope(scope)
        loop.close()


def test_total_run_and_app_bounds_are_explicit_and_release_is_idempotent():
    loop, hub = (
        asyncio.new_event_loop(),
        RunEventHub(capacity=2, per_run=1, max_scopes=1),
    )
    scope = hub.open_scope(loop)
    try:
        first = hub.subscribe(scope, "alice", "one")
        with pytest.raises(EvidenceError, match="容量"):
            hub.subscribe(scope, "bob", "one")
        hub.subscribe(scope, "alice", "two")
        with pytest.raises(EvidenceError, match="容量"):
            hub.subscribe(scope, "alice", "three")
        with pytest.raises(EvidenceError, match="容量"):
            hub.open_scope(loop)
        first.close()
        hub.subscribe(scope, "bob", "three")
        hub.close_scope(scope)
        hub.close_scope(scope)
        assert hub.statistics()["subscriptions"] == 0
    finally:
        hub.close_scope(scope)
        loop.close()


def test_closed_loop_drops_scope_without_new_cache_or_pending_callback():
    loop, hub = asyncio.new_event_loop(), RunEventHub()
    scope = hub.open_scope(loop)
    value = hub.subscribe(scope, "alice", "run")
    loop.close()
    hub.publish("run", 1)
    assert value.closed and hub.statistics()["scopes"] == 0


def test_per_app_subscription_bound_does_not_exhaust_other_apps():
    loop, hub = asyncio.new_event_loop(), RunEventHub(capacity=4, per_scope=2)
    first, second = hub.open_scope(loop), hub.open_scope(loop)
    try:
        hub.subscribe(first, "alice", "one")
        hub.subscribe(first, "alice", "two")
        with pytest.raises(EvidenceError, match="容量"):
            hub.subscribe(first, "alice", "three")
        hub.subscribe(second, "bob", "three")
        assert hub.statistics()["subscriptions"] == 3
    finally:
        hub.close_scope(first)
        hub.close_scope(second)
        loop.close()


@pytest.mark.parametrize(
    "payload",
    [
        "",
        ":1",
        "run:0",
        "run:-1",
        "run:01",
        "run:１２",
        "run: 1",
        "run:9223372036854775808",
        "a" * 201 + ":1",
        "run:NaN",
    ],
)
def test_invalid_notices_are_not_a_cursor_or_cache(payload):
    assert parse_notice(payload) is None


def test_notice_uses_last_colon_and_exact_bounded_integer():
    assert parse_notice("run:has:colon:123") == ("run:has:colon", 123)


def test_process_service_reuses_one_listener_and_rejects_conflicting_database(
    monkeypatch,
):
    constructed = []

    class Listener:
        def __init__(self, dsn, hub):
            self.starts = self.closes = 0
            constructed.append(self)

        def start(self):
            self.starts += 1

        def close(self):
            self.closes += 1

    monkeypatch.setattr(
        "mingjing_core.application.run_event_service.EventListener", Listener
    )

    async def exercise():
        repo = SimpleNamespace(dsn="host=127.0.0.1 port=55480 dbname=synthetic")
        first, second = acquire_event_hints(repo), acquire_event_hints(repo)
        try:
            assert len(constructed) == 1 and constructed[0].starts == 1
            with pytest.raises(EvidenceError, match="配置冲突"):
                acquire_event_hints(SimpleNamespace(dsn=repo.dsn + " user=other"))
            first.close()
            assert constructed[0].closes == 0
            value = second.subscribe(repo, "alice", "run")
            value.close()
            second.close()
            second.close()
            assert constructed[0].closes == 1
        finally:
            first.close()
            second.close()

    asyncio.run(exercise())

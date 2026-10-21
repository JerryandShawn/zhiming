"""Local PG is the real queue/lease authority; workers use scripted runtimes only."""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.dispatcher_claims import DispatcherClaims
from mingjing_core.application.dispatcher_notifications import (
    NotificationBridge,
    RunSignals,
)
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import LeaseConflict, ScopeError
from mingjing_core.repositories.dispatch_hooks import notify_run
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

from .test_loop_cycle_support import ScriptedPort, SyntheticMeter, answer


@pytest.fixture(name="dispatch_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def reject(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dispatcher PG tests forbid external HTTP")

    monkeypatch.setattr(httpx.Client, "send", reject)
    for key in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    yield p2_repo


def queued(
    repo: PostgresRepository, *, owner: str = "alice", thread: str = "life:self", lane: str = "interactive"
) -> dict:
    source = MemoryService(repo).receive(
        owner, content="合成调度问题", source_id=uuid.uuid4().hex, at=get_clock().now()
    )
    with repo.transaction(owner) as connection:
        run = repo.queue_run(
            owner, uuid.uuid4().hex, {"message": source["content"], "source_message_id": source["id"], "case_ids": []}
        )
        connection.execute(
            sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s,lane=%s WHERE owner=%s AND id=%s").format(
                repo.table("core_runs")
            ),
            (thread, lane, owner, run["id"]),
        )
    return repo.fetch_run(owner, run["id"])


def until(predicate: Any, timeout: float = 3) -> None:
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= end:
            pytest.fail("本机调度等待超过测试上限")
        threading.Event().wait(0.01)


def test_background_cap_preserves_interactive_capacity_and_global_three(dispatch_repo: PostgresRepository) -> None:
    repo, claims = dispatch_repo, DispatcherClaims(dispatch_repo)
    first = queued(repo, thread="background:one", lane="background")
    queued(repo, thread="background:two", lane="background")
    assert claims.claim("background")["id"] == first["id"]
    assert claims.claim("background") is None
    queued(repo, thread="interactive:one")
    queued(repo, thread="interactive:two")
    queued(repo, thread="interactive:three")
    assert claims.claim("interactive") and claims.claim("interactive")
    assert claims.claim("interactive") is None


def test_two_workers_and_direct_claim_share_thread_fence(dispatch_repo: PostgresRepository) -> None:
    repo = dispatch_repo
    runs = [queued(repo), queued(repo)]
    other = PostgresRepository(repo.dsn, schema=repo.schema, initialize=False)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda r: DispatcherClaims(r).claim("interactive"), (repo, other)))
        assert sum(row is not None for row in results) == 1
        pending = next(row for row in runs if row["id"] != next(row for row in results if row)["id"])
        with pytest.raises(LeaseConflict, match="线程"):
            repo.claim_run("alice", pending["id"])
        claimed = next(row for row in results if row)
        repo.fail_run("alice", claimed["id"], "合成轮次结束", claimed["lease_token"])
        assert DispatcherClaims(repo).claim("interactive")["id"] == pending["id"]
    finally:
        other.close()


def test_other_owner_same_thread_name_does_not_block(dispatch_repo: PostgresRepository) -> None:
    queued(dispatch_repo)
    queued(dispatch_repo, owner="bob")
    claims = DispatcherClaims(dispatch_repo)
    assert claims.claim("interactive") and claims.claim("interactive")


def test_queue_notification_is_commit_bound_and_scoped(dispatch_repo: PostgresRepository) -> None:
    repo, wake, signals = dispatch_repo, threading.Event(), RunSignals()
    bridge = NotificationBridge(repo, wake.set, signals)
    bridge.start()
    try:
        assert bridge.ready.wait(2)
        with pytest.raises(RuntimeError), repo.transaction("alice"):
            queued(repo)
            raise RuntimeError("synthetic rollback")
        assert not wake.wait(0.2)
        queued(repo)
        assert wake.wait(2)
        wake.clear()
        bridge._notice("mj_run_queued", json.dumps({"schema": "other_schema", "run_id": "synthetic"}))
        assert not wake.is_set()
    finally:
        bridge.close()


def test_cancel_notify_is_not_authority_and_owner_is_checked(dispatch_repo: PostgresRepository) -> None:
    repo, signals = dispatch_repo, RunSignals()
    run = queued(repo)
    event = signals.event("alice", run["id"])
    bridge = NotificationBridge(repo, lambda: None, signals)
    payload = json.dumps({"schema": repo.schema, "run_id": run["id"]})
    bridge._notice("mj_run_cancel", payload)
    assert not event.is_set()
    with pytest.raises(ScopeError):
        DispatcherCancellation(repo, signals).request("bob", run["id"])
    stopped = DispatcherCancellation(repo, signals).request("alice", run["id"])
    assert stopped["status"] == "cancelled" and event.is_set()
    assert DispatcherClaims(repo).claim("interactive") is None


def test_dispatcher_recovers_expired_lease_and_polls_when_listener_missing(dispatch_repo: PostgresRepository) -> None:
    repo = dispatch_repo
    run = queued(repo)
    claimed = repo.claim_run("alice", run["id"], lease_seconds=150)
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE id=%s").format(repo.table("core_runs")),
            (claimed["id"],),
        )
    port = ScriptedPort([answer("调度恢复完成")])
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    dispatcher = AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime))
    try:
        assert dispatcher.tick() == 1
        until(lambda: repo.fetch_run("alice", run["id"])["status"] == "succeeded")
        assert len(port.requests) == 1
        assert repo.fetch_run("alice", run["id"])["attempts"] == 2
    finally:
        dispatcher.close()


def test_cancel_notification_payload_contains_no_request_body(dispatch_repo: PostgresRepository) -> None:
    repo = dispatch_repo
    with repo.transaction() as connection:
        notify_run(connection, repo.schema, "run_synthetic", cancel=True)
    bridge = NotificationBridge(repo, lambda: None, RunSignals())
    for payload in ("null", "[]", "bad-json", '{"schema":"x","run_id":"a","body":"hidden"}'):
        bridge._notice("mj_run_cancel", payload)


def test_real_cancel_notification_reaches_other_process_signals(dispatch_repo: PostgresRepository) -> None:
    repo, signals = dispatch_repo, RunSignals()
    run = queued(repo)
    event = signals.event("alice", run["id"])
    bridge = NotificationBridge(repo, lambda: None, signals)
    bridge.start()
    try:
        assert bridge.ready.wait(2)
        DispatcherCancellation(repo).request("alice", run["id"])
        assert event.wait(2)
    finally:
        bridge.close()


def test_reserved_lanes_allow_background_after_interactive_burst(dispatch_repo: PostgresRepository) -> None:
    repo, claims = dispatch_repo, DispatcherClaims(dispatch_repo)
    for index in range(3):
        queued(repo, thread=f"interactive:{index}")
    queued(repo, thread="background:one", lane="background")
    assert claims.claim("interactive") and claims.claim("interactive")
    assert claims.claim("interactive") is None
    assert claims.claim("background")

"""A real actor persists quiet fragments and rejects stale timers using actual PG."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import httpx
import pytest
from psycopg import sql
from stream_timer_support import QuietPort, launch, read_deltas

from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.run_event_stream_state import STATE_KEY, StreamState
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import SystemClock, get_clock, set_clock
from mingjing_core.agent.crisis import FALLBACK_TEXT


@pytest.fixture
def timer_repo(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("timer tests forbid physical provider HTTP and subprocess")

    monkeypatch.setattr(httpx.Client, "send", blocked)
    monkeypatch.setattr(httpx.AsyncClient, "send", blocked)
    monkeypatch.setattr("subprocess.run", blocked)
    for name in ("KIMI_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY", "LANGSMITH_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    previous = get_clock()
    set_clock(SystemClock())
    try:
        yield p2_repo
    finally:
        set_clock(previous)


def test_quiet_provider_fragment_reaches_pg_before_next_fragment(timer_repo: PostgresRepository) -> None:
    repo, port = timer_repo, QuietPort()
    run, thread, observed = launch(repo, port)
    try:
        deadline = time.monotonic() + 0.75
        while time.monotonic() < deadline and not read_deltas(repo, run):
            time.sleep(0.005)
        latency = time.monotonic() - port.quiet_at
        assert read_deltas(repo, run) == ["静默合成片"] and not port.release.is_set()
        assert 0.05 <= latency < 0.75
    finally:
        port.release.set()
        thread.join(1)
    assert not thread.is_alive() and "error_type" not in observed
    assert observed["result"]["text"] == "静默合成片结束" and port.calls == 1
    assert read_deltas(repo, run) == ["静默合成片", "结束"]
    assert repo.fetch_run("alice", run["id"])["usage"][STATE_KEY]["closed"] is True


@pytest.mark.parametrize("change", ["version", "cancel", "revoke", "lease"])
def test_independent_timer_failure_cancels_a_quiet_port_without_periodic_control(
    timer_repo: PostgresRepository, change: str
) -> None:
    repo, port = timer_repo, QuietPort()
    run, thread, observed = launch(repo, port)
    claimed = repo.fetch_run("alice", run["id"])
    try:
        if change == "version":
            source = repo.get("alice", "message", run["request"]["source_message_id"])
            repo.update("alice", "message", source["id"], {"content": "合成更改"}, expected_revision=source["revision"])
            assert repo.fetch_run("alice", run["id"])["lease_token"] == claimed["lease_token"]
        elif change == "cancel":
            DispatcherCancellation(repo).request("alice", run["id"])
        elif change == "revoke":
            repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
        else:
            with repo.transaction("alice") as connection:
                connection.execute(
                    sql.SQL("UPDATE {} SET lease_until=now()-interval '1 second' WHERE owner='alice' AND id=%s").format(
                        repo.table("core_runs")
                    ),
                    (run["id"],),
                )
            repo.claim_run("alice", run["id"])
        assert port.cancelled.wait(0.75), "only the independent actor can signal this quiet provider"
    finally:
        port.release.set()
        thread.join(1)
    assert not thread.is_alive()
    assert observed.get("result") is None
    assert read_deltas(repo, run) == [] and port.calls == 1
    assert repo.fetch_run("alice", run["id"])["result"] is None


@pytest.mark.parametrize("message", ["合成静默问题", "合成测试：我想结束生命"])
def test_timer_owner_lock_contention_stops_without_flushing_old_buffer(
    timer_repo: PostgresRepository, message: str
) -> None:
    repo, port = timer_repo, QuietPort()
    run, thread, observed = launch(repo, port, message=message)
    try:
        with repo.pool.connection() as other, other.transaction():
            other.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (repo.schema + ":alice",))
            assert port.cancelled.wait(0.75)
            assert read_deltas(repo, run) == []
    finally:
        port.release.set()
        thread.join(1)
    assert not thread.is_alive()
    assert observed.get("result") is None
    assert read_deltas(repo, run) == [] and repo.fetch_run("alice", run["id"])["result"] is None


def test_real_provider_unavailable_is_distinct_from_actor_persistence_failure(timer_repo: PostgresRepository) -> None:
    repo, port = timer_repo, QuietPort(fail_immediately=True)
    run, thread, observed = launch(repo, port)
    thread.join(1)
    assert not thread.is_alive() and "error_type" not in observed
    # First release contract (user decision 10-24): provider failure answers with the neutral fallback.
    assert observed["result"]["text"] == FALLBACK_TEXT
    assert read_deltas(repo, run) == [] and port.calls == 1
    assert repo.fetch_run("alice", run["id"])["usage"][STATE_KEY]["closed"] is False


def test_provider_failure_during_unknown_timer_write_cannot_publish_partial(
    timer_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    original = StreamState.commit

    def blocked(self, step, expected, chunk, drafts, *, closed=False, stopped=None):
        if chunk == "" and not closed:
            entered.set()
            assert release.wait(2), "test must release unknown timer write"
            raise EvidenceError("合成定时写入失败")
        return original(self, step, expected, chunk, drafts, closed=closed, stopped=stopped)

    monkeypatch.setattr(StreamState, "commit", blocked)
    repo, port = timer_repo, QuietPort()
    run, thread, observed = launch(repo, port)
    try:
        assert entered.wait(1)
        port.unavailable.set()
        thread.join(0.5)
        assert not thread.is_alive(), "failed finish must not wait for timer acknowledgement"
        assert observed.get("result") is None
        assert read_deltas(repo, run) == [] and repo.fetch_run("alice", run["id"])["result"] is None
    finally:
        release.set()
        port.release.set()
        thread.join(1)

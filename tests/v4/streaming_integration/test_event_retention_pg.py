"""M5 acceptance: real PG, offline model, and an explicit manual sweep.

The archived initial baseline uses the old maintenance entry point. Root approved
the explicit EventRetentionSweep act seam and real terminal anchor; observable
assertions remain unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.event_retention import EventRetentionSweep
from mingjing_core.application.run_event_read import RunEventReader
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.event_retention_metadata import terminal_anchor
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from mingjing_core.timekit.timestamps import history_instant
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, answer
from tests.v4.agent.test_runtime_assembly_pg import configure, service
from tests.v4.streaming_integration.test_event_notify_pg import claimed, started, stored
from tests.v4.streaming_integration.test_event_notify_pg import (
    event_repo as source_repo_fixture,
)


@pytest.fixture(name="retention_repo")
def repository_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgresRepository]:
    original = get_clock()
    try:
        yield from source_repo_fixture.__wrapped__(p2_repo, monkeypatch)
    finally:
        set_clock(original)


def completed(repo: PostgresRepository) -> dict[str, Any]:
    configure(repo)
    core = service(repo, ScriptedPort([answer("合成保留策略终稿")]))
    queued = core.submit(owner="alice", request_id=uuid.uuid4().hex, message="合成保留策略问题")
    result = core.execute("alice", queued["id"])
    run = repo.fetch_run("alice", queued["id"])
    assert run["status"] == "succeeded" and result == run["result"]
    assert any(row["kind"] == "text_delta" for row in stored(repo, run))
    return run


def sweep(repo: PostgresRepository) -> None:
    EventRetentionSweep(repo).tick()


def age_from_baseline(run: dict[str, Any], elapsed: timedelta) -> None:
    anchor = terminal_anchor(run)
    assert anchor is not None
    baseline = history_instant(anchor["at"])
    assert baseline is not None
    set_clock(FrozenClock(baseline + elapsed))


def remove_rows(repo: PostgresRepository, run: dict[str, Any], sequences: list[int]) -> None:
    # A synthetic storage fault has no retention proof and cannot authorize resume.
    with repo.transaction(run["owner"]) as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND run_id=%s AND seq=ANY(%s)").format(
                repo.table("core_run_events")
            ),
            (run["owner"], run["id"], sequences),
        )


@pytest.mark.parametrize(
    "elapsed",
    [timedelta(hours=24) - timedelta(seconds=1), timedelta(hours=24, seconds=1)],
)
def test_24_hour_policy_physically_deletes_only_text_delta(
    retention_repo: PostgresRepository, elapsed: timedelta
) -> None:
    repo = retention_repo
    run = completed(repo)
    before = stored(repo, run)
    assistant = repo.get("alice", "message", run["result"]["message_id"])
    age_from_baseline(run, elapsed)
    sweep(repo)
    actual = stored(repo, run)
    expected = [row for row in before if row["kind"] != "text_delta"] if elapsed.days else before
    assert actual == expected
    assert repo.fetch_run("alice", run["id"])["result"] == run["result"]
    assert repo.get("alice", "message", assistant["id"]) == assistant


def test_30_day_policy_physically_deletes_events_and_reader_never_recreates_final(
    retention_repo: PostgresRepository,
) -> None:
    repo = retention_repo
    run = completed(repo)
    before = stored(repo, run)
    assert any(row["kind"] == "final" for row in before)
    age_from_baseline(run, timedelta(days=30, seconds=1))
    sweep(repo)
    assert stored(repo, run) == []
    reader = RunEventReader(repo, "alice", run["id"])
    for _ in range(2):
        actual, last, done = reader.page(0)
        reader.ensure_terminal()
        assert actual == [] and last == 0 and done
        assert stored(repo, run) == []
    with pytest.raises(EvidenceError, match="游标"):
        reader.validate_cursor(before[-1]["seq"])
    assert repo.fetch_run("alice", run["id"])["result"] == run["result"]
    assert repo.get("alice", "message", run["result"]["message_id"])["role"] == "assistant"


def test_real_tail_loss_does_not_allow_sequence_reuse_after_retry(
    retention_repo: PostgresRepository,
) -> None:
    repo = retention_repo
    run = claimed(repo)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    events.send("text_delta", {"text": "合成第一片段"})
    events.send("text_delta", {"text": "合成第二片段"})
    old_max = stored(repo, run)[-1]["seq"]
    repo.fail_run("alice", run["id"], "synthetic", run["lease_token"])
    remove_rows(repo, run, [2, 3])
    repo.prepare_retry("alice", run["id"])
    retry = repo.claim_run("alice", run["id"])
    RuntimeEvents(repo, retry, None).send("status", {"text": "正在继续", "phase": "thinking"})
    assert stored(repo, run)[-1]["seq"] > old_max


def test_deleted_cursor_needs_exact_cleanup_proof_not_a_range(
    retention_repo: PostgresRepository,
) -> None:
    repo = retention_repo
    run = claimed(repo)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    for _ in range(3):
        events.send("text_delta", {"text": "合成精确删除证明片段"})
    remove_rows(repo, run, [3])
    failed = repo.fail_run("alice", run["id"], "synthetic", run["lease_token"])
    age_from_baseline(failed, timedelta(hours=24, seconds=1))
    sweep(repo)
    assert [row["seq"] for row in stored(repo, run)] == [1]
    reader = RunEventReader(repo, "alice", run["id"])
    reader.validate_cursor(2)
    reader.validate_cursor(4)
    for unknown in (3, 5):
        with pytest.raises(EvidenceError, match="事件游标不可用，请重新读取运行状态"):
            reader.validate_cursor(unknown)
    with pytest.raises(ScopeError):
        RunEventReader(repo, "bob", run["id"])


def test_withdrawn_event_metadata_survives_both_retention_windows(
    retention_repo: PostgresRepository,
) -> None:
    repo = retention_repo
    run = claimed(repo)
    events = RuntimeEvents(repo, run, None)
    events.send("started", started(run))
    events.send("text_delta", {"text": "合成将被撤销片段"})
    original = [(row["seq"], row["kind"]) for row in stored(repo, run)]
    withdrawn_at = get_clock().now()
    repo.invalidate_derived("alice", [], [run["request"]["source_message_id"]])
    revoked = repo.fetch_run("alice", run["id"])
    assert revoked["status"] == "revoked"
    for age in (timedelta(hours=24, seconds=1), timedelta(days=30, seconds=1)):
        # Withdrawal intentionally keeps its original path and does not fabricate
        # a successful-commit anchor for a never-committed running attempt.
        set_clock(FrozenClock(withdrawn_at + age))
        sweep(repo)
        rows = stored(repo, run)
        assert [(row["seq"], row["kind"]) for row in rows] == original
        assert all(row["payload"] == {} for row in rows)
        assert repo.fetch_run("alice", run["id"])["result"] is None


def test_cleanup_cannot_expire_live_run_from_event_creation_time(
    retention_repo: PostgresRepository,
) -> None:
    repo = retention_repo
    run = claimed(repo)
    RuntimeEvents(repo, run, None).send("started", started(run))
    RuntimeEvents(repo, run, None).send("text_delta", {"text": "合成仍在运行片段"})
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET created_at=created_at-interval '31 days' WHERE owner=%s AND run_id=%s").format(
                repo.table("core_run_events")
            ),
            ("alice", run["id"]),
        )
    before = stored(repo, run)
    sweep(repo)
    assert stored(repo, run) == before
    assert repo.fetch_run("alice", run["id"])["status"] == "running"


@pytest.mark.parametrize("stale", [False, True])
def test_old_terminal_age_cannot_delete_requeued_attempt(retention_repo: PostgresRepository, stale: bool) -> None:
    repo = retention_repo
    run = claimed(repo)
    RuntimeEvents(repo, run, None).send("started", started(run))
    RuntimeEvents(repo, run, None).send("text_delta", {"text": "合成将继续的片段"})
    failed = repo.fail_run(
        "alice",
        run["id"],
        "synthetic",
        run["lease_token"],
        status="stale" if stale else "failed",
    )
    repo.prepare_retry("alice", run["id"])
    assert repo.fetch_run("alice", run["id"])["retry_epoch"] == run["retry_epoch"] + int(stale)
    before = stored(repo, run)
    age_from_baseline(failed, timedelta(days=31))
    sweep(repo)
    assert stored(repo, run) == before
    assert repo.fetch_run("alice", run["id"])["status"] == "queued"

"""Manual unknown-result reconciliation preserves all charged attempts."""

from __future__ import annotations

import multiprocessing
from datetime import timedelta
from typing import Any

import pytest
from psycopg import sql

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock

from .test_quota_guard_batches_pg import begin
from .test_quota_guard_pg import configure_central
from .test_quota_guard_process_pg import shutdown, worker


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def crash_evaluated(central: dict[str, Any]) -> None:
    context = multiprocessing.get_context("spawn")
    queue, hold = context.Queue(), context.Event()
    batch = dict(batch_id="batch-1", authorization_id="manual-start-1", scenario_id="S01")
    process = context.Process(target=worker, args=(central, queue, hold, "unknown-eval", "eval", 1, batch))
    try:
        process.start()
        assert queue.get(timeout=15) == ("entered", "unknown-eval", 1)
        process.terminate()
        process.join(5)
        assert process.exitcode is not None
    finally:
        shutdown([process] if process.pid else [])
        queue.close()


def test_manual_recovery_requires_both_slots_idle_and_never_refunds_or_starts(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    crash_evaluated(central)
    with (
        guard.acquire("primary", "interactive", attempt_id="foreground", provider="synthetic", model="k3-256k"),
        guard.acquire("critic", "interactive", attempt_id="critic", provider="synthetic", model="k3-256k"),
    ):
        assert guard.status()["in_flight"] == 2
        with pytest.raises(GuardRejected) as caught:
            guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="explicit-recovery")
        assert caught.value.kind == "in_flight_limit"
    with pytest.raises(GuardRejected):
        guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="manual-start-1")
    guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="explicit-recovery")
    guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="explicit-recovery")
    state = QuotaGuard(**central).status()
    assert state["window"]["total"] == 3 and state["window"]["unfinished"] == state["in_flight"] == 0
    assert state["next_batch_not_before"] is not None
    with guard.store.connect() as connection:
        row = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE attempt_id='unknown-eval'").format(guard.store.table("core_model_usage"))
        ).fetchone()
        batch = connection.execute(
            sql.SQL("SELECT * FROM {}").format(guard.store.table("core_model_batches"))
        ).fetchone()
    assert row["status"] == "unknown" and row["input_tokens"] is None and row["finished_at"] is not None
    assert batch["recovery_authorization"] == "explicit-recovery" and batch["status"] == "completed"
    with pytest.raises(GuardRejected) as caught:
        begin(guard, batch="batch-2", auth="explicit-next-batch")
    assert caught.value.kind == "batch_cooldown"


def test_manual_recovery_does_not_clear_global_stop(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    crash_evaluated(central)
    guard.record_stop("access_terminated")
    guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="explicit-recovery")
    state = QuotaGuard(**central).status()
    assert state["stop_kind"] == "access_terminated"
    assert state["window"]["total"] == 1 and state["window"]["unfinished"] == 0


def test_recovery_authorization_cannot_be_reused_for_another_batch(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    begin(guard)
    crash_evaluated(dict(central, clock=clock))
    guard.close_abandoned_batch(batch_id="batch-1", recovery_authorization_id="one-use-recovery")
    clock.advance(timedelta(minutes=20))
    begin(guard, batch="batch-2", auth="second-manual-start")
    with pytest.raises(GuardRejected) as caught:
        guard.close_abandoned_batch(batch_id="batch-2", recovery_authorization_id="one-use-recovery")
    assert caught.value.kind == "manual_start_required"
    assert guard.status()["window"]["total"] == 1

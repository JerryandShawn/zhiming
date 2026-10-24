"""Independent spawned processes share the same real PG admission authority."""

from __future__ import annotations

import multiprocessing
from typing import Any

import httpx
import pytest

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardRejected, QuotaPolicy
from mingjing_core.repositories.postgres import PostgresRepository

from .test_quota_guard_pg import configure_central


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def worker(
    params: dict[str, Any],
    queue: Any,
    release: Any,
    ident: str,
    lane: str,
    timeout: float | None,
    batch: dict[str, str] | None = None,
) -> None:
    sent = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal sent
        sent += 1
        queue.put(("entered", ident, sent))
        if release is not None and not release.wait(20):
            raise RuntimeError("SYNTHETIC_HOLD_TIMEOUT")
        return httpx.Response(200, json={"synthetic": True})

    guard = QuotaGuard(**params)
    try:
        role = {"interactive": "primary", "eval": "evaluation"}.get(lane, "background")
        with guard.acquire(
            role, lane, attempt_id=ident, provider="synthetic", model="k3-256k", timeout=timeout, **(batch or {})
        ) as attempt:
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                client.post("https://synthetic.invalid/messages", json={"synthetic": True})
            attempt.result()
    except GuardRejected as error:
        queue.put(("rejected", error.kind, sent))
    else:
        queue.put(("finished", ident, sent))


def stop_worker(params: dict[str, Any], kind: str, queue: Any) -> None:
    guard = QuotaGuard(**params)
    guard.record_stop(kind)
    queue.put(("stopped", kind))


def shutdown(processes: list[Any]) -> None:
    for process in processes:
        process.join(10)
        if process.is_alive():
            process.terminate()
            process.join(5)


def test_two_real_processes_hold_slots_and_third_times_out_before_post(central: dict[str, Any]) -> None:
    context = multiprocessing.get_context("spawn")
    queue, release = context.Queue(), context.Event()
    processes = [
        context.Process(target=worker, args=(central, queue, release, "interactive", "interactive", 1)),
        context.Process(target=worker, args=(central, queue, release, "background", "background", 1)),
    ]
    try:
        for process in processes:
            process.start()
            assert queue.get(timeout=15)[0] == "entered"
        guard = QuotaGuard(**central)
        assert guard.status()["in_flight"] == 2
        third = context.Process(target=worker, args=(central, queue, None, "third", "background", 0.2))
        processes.append(third)
        third.start()
        assert queue.get(timeout=15) == ("rejected", "in_flight_limit", 0)
        third.join(5)
        assert third.exitcode == 0 and guard.status()["window"]["total"] == 2
        release.set()
        assert queue.get(timeout=15)[0] == queue.get(timeout=15)[0] == "finished"
        for process in processes:
            process.join(5)
            assert process.exitcode == 0
        assert guard.status()["in_flight"] == guard.status()["window"]["unfinished"] == 0
    finally:
        release.set()
        shutdown(processes)
        queue.close()


@pytest.mark.parametrize("kind", ["concurrency_limited", "access_terminated", "quota_weekly", "quota_monthly"])
def test_stop_from_exited_process_rejects_fresh_process_with_zero_post(central: dict[str, Any], kind: str) -> None:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    first = context.Process(target=stop_worker, args=(central, kind, queue))
    second = context.Process(target=worker, args=(central, queue, None, "new-process", "interactive", 0))
    try:
        first.start()
        assert queue.get(timeout=15) == ("stopped", kind)
        first.join(5)
        assert first.exitcode == 0
        second.start()
        assert queue.get(timeout=15) == ("rejected", kind, 0)
        second.join(5)
        assert second.exitcode == 0
        assert QuotaGuard(**central).status()["window"]["total"] == 0
    finally:
        shutdown([process for process in (first, second) if process.pid])
        queue.close()


def test_killed_sender_releases_pg_slot_without_refunding_unknown_attempt(central: dict[str, Any]) -> None:
    context = multiprocessing.get_context("spawn")
    queue, hold = context.Queue(), context.Event()
    process = context.Process(target=worker, args=(central, queue, hold, "crashed", "background", 1))
    replacement = context.Process(target=worker, args=(central, queue, None, "replacement", "background", 1))
    try:
        process.start()
        assert queue.get(timeout=15) == ("entered", "crashed", 1)
        process.terminate()
        process.join(5)
        assert process.exitcode is not None
        replacement.start()
        assert queue.get(timeout=15) == ("entered", "replacement", 1)
        assert queue.get(timeout=15) == ("finished", "replacement", 1)
        replacement.join(5)
        assert replacement.exitcode == 0
        state = QuotaGuard(**central).status()
        assert state["in_flight"] == 0
        assert state["window"]["total"] == 2 and state["window"]["unfinished"] == 1
    finally:
        # A terminated waiter may die with Event's internal lock held on Windows.
        # Never touch its synchronization object after termination.
        shutdown([item for item in (process, replacement) if item.pid])
        queue.close()


def test_two_processes_cannot_overspend_tightened_window_during_in_flight_post(central: dict[str, Any]) -> None:
    context = multiprocessing.get_context("spawn")
    queue, release = context.Queue(), context.Event()
    params = dict(central, policy=QuotaPolicy(max_calls=1))
    first = context.Process(target=worker, args=(params, queue, release, "last-available", "interactive", 1))
    second = context.Process(target=worker, args=(params, queue, None, "over-budget", "interactive", 1))
    try:
        first.start()
        assert queue.get(timeout=15) == ("entered", "last-available", 1)
        second.start()
        assert queue.get(timeout=15) == ("rejected", "member_window_limit", 0)
        second.join(5)
        assert second.exitcode == 0
        release.set()
        assert queue.get(timeout=15) == ("finished", "last-available", 1)
        first.join(5)
        assert first.exitcode == 0
        state = QuotaGuard(**params).status()
        assert state["window"]["total"] == 1 and state["stop_kind"] == "member_window_limit"
    finally:
        release.set()
        shutdown([item for item in (first, second) if item.pid])
        queue.close()

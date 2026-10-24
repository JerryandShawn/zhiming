"""Scheduling policy is monotonic, bounded, concurrent-safe and body-free on failure."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from mingjing_core.application.maintenance_schedule import FAILURE_CODE, PrivacyMaintenanceSchedule


def test_exact_minute_boundary_and_bounded_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    calls: list[int] = []
    schedule = PrivacyMaintenanceSchedule(object(), monotonic=lambda: now[0])

    def sweep(*, limit: int) -> dict[str, int]:
        calls.append(limit)
        return {"private_threads": 1, "reminders": 0, "private_steps": 0}

    monkeypatch.setattr(schedule.maintenance, "tick", sweep)
    assert schedule.tick()["status"] == "succeeded"
    for value in (0.0, 2.0, 59.999):
        now[0] = value
        assert schedule.tick() is None
    now[0] = 60.0
    assert schedule.tick()["counts"]["private_threads"] == 1
    assert calls == [50, 50] and schedule.next_due == 120.0


def test_failure_has_safe_observable_code_and_does_not_retry_each_poll(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    now, calls = [100.0], []
    schedule = PrivacyMaintenanceSchedule(object(), monotonic=lambda: now[0])

    def failed(*, limit: int) -> dict[str, int]:
        calls.append(limit)
        raise RuntimeError("私人原话 secret://synthetic-password")

    monkeypatch.setattr(schedule.maintenance, "tick", failed)
    with caplog.at_level(logging.WARNING):
        assert schedule.tick() == {"status": "failed", "code": FAILURE_CODE}
        now[0] = 102.0
        assert schedule.tick() is None
    assert calls == [50] and schedule.failures == 1 and schedule.last_error_code == FAILURE_CODE
    assert FAILURE_CODE in caplog.text and "私人原话" not in caplog.text and "secret://" not in caplog.text
    monkeypatch.setattr(schedule.maintenance, "tick", lambda **_: {"private_threads": 0})
    now[0] = 160.0
    assert schedule.tick()["status"] == "succeeded" and schedule.last_error_code is None


def test_concurrent_tick_reserves_before_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    now = [0.0]
    schedule = PrivacyMaintenanceSchedule(object(), monotonic=lambda: now[0])
    started, release = threading.Event(), threading.Event()
    calls = []

    def sweep(*, limit: int) -> dict[str, int]:
        calls.append(limit)
        started.set()
        assert release.wait(2)
        return {"private_threads": 0}

    monkeypatch.setattr(schedule.maintenance, "tick", sweep)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(schedule.tick)
        assert started.wait(2)
        now[0] = 61.0
        assert executor.submit(schedule.tick).result(timeout=1) is None
        release.set()
        assert first.result(timeout=2)["status"] == "succeeded"
    assert calls == [50]

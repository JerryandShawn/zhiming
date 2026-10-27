"""Debounce, owner-local fallback, lease and current-source scheduling safety."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_v3 import ReflectionError, ReflectionOperation
from mingjing_core.memory2.contracts import MemoryScope

from .calendar_acceptance_support_mod import SCOPE, bundle, expected, schedule


def assert_no_enqueue(data: Any, **overrides: Any) -> None:
    try:
        result = schedule(data, **overrides)
    except ReflectionError as error:
        assert data.snapshot.sources[0].text not in str(error)
        return
    assert result.disposition in {"noop", "blocked"} and result.intent is None


def test_frozen_semantics_precede_test_implementation() -> None:
    assert len(expected()["semantic_groups"]) == 18
    assert expected()["not_derived_from_peer_tests_or_implementation_outputs"] is True


@pytest.mark.parametrize("seconds,ready", ((0, False), (599.999999, False), (600, True), (600.000001, True)))
def test_idle_10_minute_exact_utc_boundary(seconds: float, ready: bool) -> None:
    data = bundle(idle=timedelta(seconds=seconds))
    result = schedule(data)
    assert (result.disposition == "enqueue") is ready
    if ready:
        assert result.intent.trigger == "idle"
        assert result.intent.kind == "reflection" and result.intent.lane == "background"
        assert result.intent.not_before <= data.clock.now()


def test_500_random_elapsed_idle_checks_are_timezone_independent() -> None:
    rng = random.Random(3307)
    for _ in range(500):
        now = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randrange(365 * 86400))
        seconds = rng.randrange(0, 1200001) / 1000
        tz = rng.choice(("Asia/Shanghai", "Asia/Tokyo", "America/New_York", "Europe/Berlin"))
        data = bundle(now=now, idle=timedelta(seconds=seconds), timezone=tz)
        result = schedule(data, timezone=tz)
        assert (result.disposition == "enqueue") is (seconds >= 600)


@pytest.mark.parametrize("tz", ("Asia/Shanghai", "Asia/Tokyo", "America/New_York"))
@pytest.mark.parametrize("local", (date(2026, 1, 1), date(2026, 10, 21), date(2026, 12, 31)))
def test_owner_local_03_fallback_is_independent_of_idle_and_supports_catchup(tz: str, local: date) -> None:
    zone = ZoneInfo(tz)
    for hour, minute, second, ready in ((2, 59, 59, False), (3, 0, 0, True), (5, 0, 0, True)):
        now = datetime(local.year, local.month, local.day, hour, minute, second, tzinfo=zone)
        data = bundle(now=now, idle=timedelta(minutes=5), timezone=tz)
        thread = replace(data.thread, daily_completed_on=None)
        result = schedule(data, thread=thread, timezone=tz)
        assert (result.disposition == "enqueue") is ready
        if ready:
            assert result.intent.trigger == "daily"


def test_same_day_completion_suppresses_daily_without_disabling_new_idle_work() -> None:
    data = bundle(idle=timedelta(minutes=5))
    assert_no_enqueue(data)
    ready = bundle(idle=timedelta(minutes=10))
    assert schedule(ready).intent.trigger == "idle"


@pytest.mark.parametrize("local_now", ((2026, 3, 29, 4, 15), (2026, 10, 25, 3, 15)))
def test_missing_or_ambiguous_03_in_helsinki_requires_explicit_host_dst_policy(local_now: tuple[int, ...]) -> None:
    zone = ZoneInfo("Europe/Helsinki")
    now = datetime(*local_now, tzinfo=zone)
    data = bundle(now=now, idle=timedelta(minutes=20), timezone="Europe/Helsinki")
    result = schedule(data, thread=replace(data.thread, daily_completed_on=None), timezone="Europe/Helsinki")
    assert result.disposition == "blocked" and result.intent is None


@pytest.mark.parametrize(
    "changes",
    (
        {"enabled": False},
        {"quota_stopped": True},
        {"active": False},
        {"revision": 1, "current_revision": 2},
        {"scope": MemoryScope("synthetic-other-owner", SCOPE.subject_id)},
    ),
)
def test_background_permission_is_explicit_current_and_scoped(changes: dict[str, Any]) -> None:
    data = bundle()
    assert_no_enqueue(data, permit=replace(data.permit, **changes))


def test_no_permit_is_no_enqueue() -> None:
    assert_no_enqueue(bundle(), permit=None)


@pytest.mark.parametrize(
    "changes", ({"incognito": True}, {"active": False}, {"retention_scope": "temporary"}, {"running": True})
)
def test_private_temporary_inactive_or_running_thread_cannot_enqueue(changes: dict[str, Any]) -> None:
    data = bundle()
    assert_no_enqueue(data, thread=replace(data.thread, **changes))


def test_active_thread_lease_and_clock_rollback_do_not_enqueue() -> None:
    data = bundle()
    assert_no_enqueue(data, thread=replace(data.thread, lease_until=data.clock.now() + timedelta(seconds=1)))
    assert_no_enqueue(data, thread=replace(data.thread, last_observed_at=data.clock.now() + timedelta(microseconds=1)))


@pytest.mark.parametrize("changes", ({"active": False}, {"revoked": True}, {"incognito": True}, {"optout": True}))
def test_source_lifecycle_is_authoritative_not_just_thread_flags(changes: dict[str, bool]) -> None:
    data = bundle()
    source = replace(data.snapshot.sources[0], **changes)
    snapshot = replace(data.snapshot, sources=(source,))
    assert_no_enqueue(data, snapshot=snapshot)


@pytest.mark.parametrize("field", ("owner_id", "subject_id"))
def test_foreign_source_never_yields_background_intent(field: str) -> None:
    data = bundle()
    source = replace(data.snapshot.sources[0], **{field: f"synthetic-foreign-{field}"})
    assert_no_enqueue(data, snapshot=replace(data.snapshot, sources=(source,)))


def test_source_future_time_and_missing_source_never_yield_intent() -> None:
    data = bundle()
    source = replace(data.snapshot.sources[0], at=data.clock.now() + timedelta(microseconds=1))
    assert_no_enqueue(data, snapshot=replace(data.snapshot, sources=(source,)))
    assert_no_enqueue(data, snapshot=replace(data.snapshot, sources=()))


def test_stable_operation_and_matching_ledger_are_idempotent() -> None:
    data = bundle()
    one, two = schedule(data), schedule(data)
    assert one.intent.operation_id == two.intent.operation_id
    assert one.intent.input_fingerprint == two.intent.input_fingerprint
    ledger = ReflectionOperation(SCOPE, data.thread.id, one.intent.operation_id, one.intent.input_fingerprint)
    replay = schedule(data, operations=(ledger,))
    assert replay.disposition == "noop" and replay.intent is None and replay.replayed is True


def test_processed_current_cursor_does_not_enqueue_duplicate_work() -> None:
    data = bundle()
    first = schedule(data)
    thread = replace(
        data.thread, processed_sources=first.intent.source_manifest, processed_epoch=data.snapshot.source_epoch
    )
    assert_no_enqueue(data, thread=thread)


def test_source_epoch_change_invalidates_processed_cursor() -> None:
    data = bundle()
    first = schedule(data)
    thread = replace(
        data.thread, processed_sources=first.intent.source_manifest, processed_epoch=data.snapshot.source_epoch
    )
    snapshot = replace(data.snapshot, source_epoch=data.snapshot.source_epoch + 1)
    result = schedule(data, thread=thread, snapshot=snapshot)
    assert result.disposition == "enqueue"
    assert result.intent.source_epoch != first.intent.source_epoch

"""FrozenClock scheduling intentions only. No run, model call or queue is created."""

import random
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.application.reflection_v3 import (
    BackgroundPermit,
    ReflectionError,
    ReflectionOperation,
    ThreadState,
    schedule_reflection,
)
from mingjing_core.application.reflection_v3.source_policy import source_cursor
from mingjing_core.memory2.contracts import MemoryScope, MemorySnapshot, MemorySource
from mingjing_core.timekit.clock import FrozenClock

SCOPE = MemoryScope("synthetic-reflection-owner", "synthetic-reflection-self")
AT = datetime(2026, 10, 20, 18, tzinfo=UTC)  # 02:00 next day in Shanghai.


def values(at=AT):
    source = MemorySource(
        "synthetic-reflection-source", SCOPE.owner_id, SCOPE.subject_id, "合成验收原话", at - timedelta(hours=1)
    )
    snapshot = MemorySnapshot(SCOPE, sources=(source,), revision=1, source_epoch=2)
    thread = ThreadState(SCOPE, "synthetic-thread", 1, at - timedelta(minutes=10), (source.id,))
    permit = BackgroundPermit(SCOPE, 3, 3, enabled=True, quota_stopped=False)
    return dict(snapshot=snapshot, thread=thread, scope=SCOPE, clock=FrozenClock(at), permit=permit)


@pytest.mark.parametrize("seconds,queued", [(599, False), (600, True), (601, True)])
def test_idle_ten_minute_boundary(seconds, queued):
    args = values()
    args["thread"] = replace(args["thread"], last_activity_at=AT - timedelta(seconds=seconds))
    result = schedule_reflection(**args)
    assert (result.disposition == "enqueue") is queued
    if queued:
        assert result.intent.trigger == "idle" and result.intent.not_before == AT + timedelta(seconds=600 - seconds)


@pytest.mark.parametrize("tz", ["Asia/Shanghai", "Asia/Tokyo", "UTC", "America/New_York", "Europe/Berlin"])
@pytest.mark.parametrize("hour,minute,expected", [(2, 59, False), (3, 0, True), (3, 1, True)])
def test_daily_three_am_is_owner_local_and_not_host_timezone(tz, hour, minute, expected):
    at = datetime(2026, 10, 21, hour, minute, tzinfo=ZoneInfo(tz)).astimezone(UTC)
    args = values(at)
    args["thread"] = replace(args["thread"], last_activity_at=at - timedelta(minutes=1))
    result = schedule_reflection(**args, timezone=tz)
    assert (result.disposition == "enqueue") is expected
    if expected:
        assert result.intent.trigger == "daily" and result.intent.not_before.astimezone(ZoneInfo(tz)).hour == 3


@pytest.mark.parametrize(
    "changes", [{"enabled": False}, {"quota_stopped": True}, {"active": False}, {"current_revision": 4}]
)
def test_current_background_configuration_is_mandatory(changes):
    args = values()
    args["permit"] = replace(args["permit"], **changes)
    assert schedule_reflection(**args).disposition == "blocked"
    args["permit"] = None
    assert schedule_reflection(**args).reason == "current_background_permission_required"


@pytest.mark.parametrize(
    "changes",
    [
        {"active": False},
        {"incognito": True},
        {"id": "incognito:synthetic"},
        {"retention_scope": "temporary"},
        {"running": True},
        {"lease_until": AT + timedelta(seconds=1)},
        {"last_observed_at": AT + timedelta(seconds=1)},
        {"last_activity_at": AT + timedelta(seconds=1)},
    ],
)
def test_thread_privacy_running_and_clock_rollback_are_blocked(changes):
    args = values()
    args["thread"] = replace(args["thread"], **changes)
    assert schedule_reflection(**args).disposition == "blocked"


@pytest.mark.parametrize(
    "changes",
    [{"active": False}, {"revoked": True}, {"incognito": True}, {"optout": True}, {"at": AT + timedelta(seconds=1)}],
)
def test_unavailable_sources_never_enter_intent_manifest(changes):
    args = values()
    source = replace(args["snapshot"].sources[0], **changes)
    args["snapshot"] = replace(args["snapshot"], sources=(source,))
    result = schedule_reflection(**args)
    assert result.disposition == "noop" and result.intent is None


def test_current_cursor_has_no_idle_repeat_but_epoch_change_requires_replanning():
    args = values()
    cursor = source_cursor(args["snapshot"].sources[0])
    args["thread"] = replace(args["thread"], processed_sources=(cursor,), processed_epoch=2)
    assert schedule_reflection(**args).disposition == "noop"
    args["snapshot"] = replace(args["snapshot"], source_epoch=3)
    assert schedule_reflection(**args).disposition == "enqueue"


def test_queued_operation_is_idempotent_and_other_current_thread_work_blocks():
    args = values()
    intent = schedule_reflection(**args).intent
    record = ReflectionOperation(SCOPE, intent.thread_id, intent.operation_id, intent.input_fingerprint)
    replay = schedule_reflection(**args, operations=(record,))
    assert replay.disposition == "noop" and replay.replayed and replay.intent is None
    pending = replace(record, operation_id="synthetic-other-operation")
    assert schedule_reflection(**args, operations=(pending,)).disposition == "blocked"
    with pytest.raises(ReflectionError):
        schedule_reflection(**args, operations=(replace(record, input_fingerprint="0" * 64),))
    with pytest.raises(ReflectionError):
        schedule_reflection(**args, operations=(replace(record, thread_id="synthetic-other-thread"),))


def test_daily_completion_rolls_at_local_midnight_and_clock_backwards_is_blocked():
    at = datetime(2026, 10, 21, 20, tzinfo=UTC)  # 04:00 on the next local day.
    args = values(at)
    args["thread"] = replace(
        args["thread"],
        processed_sources=(source_cursor(args["snapshot"].sources[0]),),
        processed_epoch=2,
        daily_completed_on=date(2026, 10, 22),
    )
    assert schedule_reflection(**args).disposition == "noop"
    args["thread"] = replace(args["thread"], daily_completed_on=date(2026, 10, 21))
    assert schedule_reflection(**args).intent.trigger == "daily"
    args["thread"] = replace(args["thread"], daily_completed_on=date(2026, 10, 23))
    assert schedule_reflection(**args).disposition == "blocked"


@pytest.mark.parametrize("at", [datetime(2026, 3, 29, 1, 30, tzinfo=UTC), datetime(2026, 10, 25, 1, 30, tzinfo=UTC)])
def test_helsinki_nonexistent_or_folded_three_am_does_not_choose_an_instant(at):
    args = values(at)
    result = schedule_reflection(**args, timezone="Europe/Helsinki")
    assert result.disposition == "blocked" and result.reason == "daily_wall_time_needs_host_policy"


def test_thousand_elapsed_idle_properties_with_frozen_clock():
    rng = random.Random(337)
    for _ in range(1000):
        seconds = rng.randrange(0, 3600)
        args = values()
        args["thread"] = replace(args["thread"], last_activity_at=AT - timedelta(seconds=seconds))
        assert (schedule_reflection(**args).disposition == "enqueue") is (seconds >= 600)

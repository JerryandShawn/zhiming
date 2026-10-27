"""Produce one candidate enqueue intention. The host must atomically recheck guards and acquire a thread lock."""

from collections.abc import Sequence
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.memory2.contracts import MemoryScope, MemorySnapshot
from mingjing_core.scheduling.recurrence_contracts import RecurrenceRule
from mingjing_core.scheduling.recurrence_wall import wall_instants
from mingjing_core.timekit.clock import Clock

from .intent_guard import intent_fingerprint
from .schedule_contracts import (
    BackgroundPermit,
    ProcessedSource,
    ReflectionIntent,
    ReflectionOperation,
    ScheduleDecision,
    ThreadState,
)
from .source_policy import source_cursor, source_reason
from .validation import ReflectionError, instant, scope_snapshot, typed_tuple


def schedule_reflection(
    *,
    snapshot: MemorySnapshot,
    thread: ThreadState,
    scope: MemoryScope,
    clock: Clock,
    permit: BackgroundPermit | None = None,
    operations: Sequence[ReflectionOperation] = (),
    timezone: str = "Asia/Shanghai",
) -> ScheduleDecision:
    scope_snapshot(snapshot, scope)
    now = instant(clock.now())
    ledger = typed_tuple(operations, ReflectionOperation)
    reason = _blocked(thread, permit, scope, now)
    if reason:
        return ScheduleDecision("blocked", reason)
    if len({row.operation_id for row in ledger}) != len(ledger) or any(row.scope != scope for row in ledger):
        raise ReflectionError("operation_ledger_invalid")
    if any(snapshot.source(sid) is None for sid in thread.source_ids):
        return ScheduleDecision("blocked", "current_thread_source_missing")
    manifest = tuple(
        sorted(
            (
                source_cursor(source)
                for sid in thread.source_ids
                if (source := snapshot.source(sid)) is not None and source_reason(source, now) is None
            ),
            key=lambda item: item.id,
        )
    )
    changed = set(manifest) != set(thread.processed_sources) or snapshot.source_epoch != thread.processed_epoch
    if not manifest and not (thread.processed_epoch is not None and snapshot.source_epoch != thread.processed_epoch):
        return ScheduleDecision("noop", "no_authorized_thread_content")
    due = _due(thread, now, timezone, changed)
    if isinstance(due, ScheduleDecision):
        return due
    return _candidate(scope, thread, snapshot, permit, manifest, ledger, due, timezone)


def _due(thread: ThreadState, now: datetime, timezone: str, changed: bool) -> tuple[str, datetime] | ScheduleDecision:
    try:
        local = now.astimezone(ZoneInfo(timezone))
    except (ValueError, TypeError, KeyError):
        raise ReflectionError("timezone_invalid") from None
    if thread.daily_completed_on is not None and thread.daily_completed_on > local.date():
        return ScheduleDecision("blocked", "daily_cursor_in_future")
    daily = local.time().replace(tzinfo=None) >= time(3) and thread.daily_completed_on != local.date()
    if not daily and (not changed or now - thread.last_activity_at < timedelta(minutes=10)):
        return ScheduleDecision("noop", "idle_not_due_or_cursor_current")
    if not daily:
        return "idle", thread.last_activity_at + timedelta(minutes=10)
    values = wall_instants(local.date(), RecurrenceRule("daily", time(3), timezone))
    if len(values) != 1:
        return ScheduleDecision("blocked", "daily_wall_time_needs_host_policy")
    return "daily", values[0]


def _candidate(
    scope: MemoryScope,
    thread: ThreadState,
    snapshot: MemorySnapshot,
    permit: BackgroundPermit,
    manifest: tuple[ProcessedSource, ...],
    ledger: tuple[ReflectionOperation, ...],
    due: tuple[str, datetime],
    timezone: str,
) -> ScheduleDecision:
    trigger, not_before = due
    fingerprint = intent_fingerprint(scope, thread, snapshot, permit, manifest, trigger, not_before, timezone)
    operation_id = "reflection:" + fingerprint
    prior = next((row for row in ledger if row.operation_id == operation_id), None)
    if prior is not None:
        if prior.thread_id != thread.id or prior.input_fingerprint != fingerprint:
            raise ReflectionError("operation_input_changed")
        return ScheduleDecision("noop", "operation_already_recorded", replayed=True)
    if any(row.thread_id == thread.id and row.state in {"queued", "running"} for row in ledger):
        return ScheduleDecision("blocked", "thread_work_already_queued")
    intent = ReflectionIntent(
        scope,
        thread.id,
        operation_id,
        fingerprint,
        trigger,
        not_before,
        snapshot.revision,
        snapshot.source_epoch,
        thread.revision,
        permit.revision,
        manifest,
        timezone=timezone,
    )
    return ScheduleDecision("enqueue", "candidate_enqueue_only", intent)


def _blocked(thread: ThreadState, permit: BackgroundPermit | None, scope: MemoryScope, now: datetime) -> str | None:
    if not isinstance(thread, ThreadState) or thread.scope != scope:
        raise ReflectionError("thread_scope_mismatch")
    if permit is None:
        return "current_background_permission_required"
    if not isinstance(permit, BackgroundPermit) or permit.scope != scope:
        raise ReflectionError("permit_scope_mismatch")
    if not permit.active or not permit.enabled or permit.quota_stopped or permit.revision != permit.current_revision:
        return "background_permission_stopped_or_stale"
    if (
        not thread.active
        or thread.incognito
        or thread.id.startswith("incognito:")
        or thread.retention_scope != "persistent"
    ):
        return "thread_not_persistent"
    if thread.last_activity_at > now or (thread.last_observed_at is not None and thread.last_observed_at > now):
        return "clock_before_observed_activity"
    if thread.running or (thread.lease_until is not None and thread.lease_until > now):
        return "thread_run_or_lease_active"
    return None

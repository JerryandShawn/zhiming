"""The enqueue fingerprint binds the precise current input; a host ledger is still required for execution."""

from datetime import datetime

from mingjing_core.memory2.contracts import MemoryScope, MemorySnapshot
from mingjing_core.timekit.clock import Clock

from .schedule_contracts import BackgroundPermit, ProcessedSource, ReflectionIntent, ThreadState
from .source_policy import source_cursor, source_reason
from .validation import ReflectionError, dataclass_json, digest, instant, scope_snapshot


def intent_fingerprint(
    scope: MemoryScope,
    thread: ThreadState,
    snapshot: MemorySnapshot,
    permit: BackgroundPermit,
    manifest: tuple[ProcessedSource, ...],
    trigger: str,
    due: datetime,
    timezone: str,
) -> str:
    return digest(
        [
            scope.owner_id,
            scope.subject_id,
            thread.id,
            thread.revision,
            thread.last_activity_at.isoformat(),
            list(thread.source_ids),
            dataclass_json(thread.processed_sources),
            thread.processed_epoch,
            dataclass_json(thread.daily_completed_on),
            snapshot.revision,
            snapshot.source_epoch,
            permit.revision,
            trigger,
            due.isoformat(),
            timezone,
            dataclass_json(manifest),
        ]
    )


def intent_reason(
    intent: ReflectionIntent,
    *,
    snapshot: MemorySnapshot,
    thread: ThreadState,
    scope: MemoryScope,
    clock: Clock,
    permit: BackgroundPermit | None,
) -> str | None:
    from .schedule import _blocked

    scope_snapshot(snapshot, scope)
    if (
        not isinstance(intent, ReflectionIntent)
        or not isinstance(thread, ThreadState)
        or intent.scope != scope
        or thread.scope != scope
        or intent.thread_id != thread.id
    ):
        raise ReflectionError("intent_scope_or_thread_mismatch")
    now = instant(clock.now())
    blocked = _blocked(thread, permit, scope, now)
    if blocked:
        return blocked
    if now < intent.not_before:
        return "intent_not_yet_due"
    if any(snapshot.source(identity) is None for identity in thread.source_ids):
        return "current_thread_source_missing"
    manifest = tuple(
        sorted(
            (
                source_cursor(source)
                for identity in thread.source_ids
                if (source := snapshot.source(identity)) is not None and source_reason(source, now) is None
            ),
            key=lambda row: row.id,
        )
    )
    expected = intent_fingerprint(
        scope, thread, snapshot, permit, manifest, intent.trigger, intent.not_before, intent.timezone
    )
    if (
        expected != intent.input_fingerprint
        or intent.operation_id != "reflection:" + expected
        or intent.source_manifest != manifest
    ):
        return "reflection_input_changed"
    if (intent.snapshot_revision, intent.source_epoch, intent.thread_revision, intent.permit_revision) != (
        snapshot.revision,
        snapshot.source_epoch,
        thread.revision,
        permit.revision,
    ):
        return "reflection_version_changed"
    return None

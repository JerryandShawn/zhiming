"""Locked process-local event log for deterministic tests; it is not a runtime authority."""

from __future__ import annotations

from threading import RLock

from mingjing_core.timekit.clock import Clock

from .event_models import EventDraft, RunEvent, RunScope, make_event
from .event_store import SequenceAllocator
from .store_contracts import AppendResult, EventCursorError, EventStoreConflict, ReplayPage, StoredEventMetadata
from .store_serialization import (
    aware_utc,
    check_operation_id,
    check_page,
    check_scope,
    check_sequence,
    draft_fingerprint,
    metadata,
)


class MemoryEventStore:
    def __init__(self, *, clock: Clock, allocator: SequenceAllocator | None = None) -> None:
        self._clock = clock
        self._allocator = allocator
        self._lock = RLock()
        self._events: dict[RunScope, list[RunEvent]] = {}
        self._operations: dict[tuple[RunScope, str], tuple[str, RunEvent]] = {}
        self._last_sequence = 0

    def append(self, scope: RunScope, draft: EventDraft, *, operation_id: str) -> AppendResult:
        operation_id = check_operation_id(operation_id)
        digest = draft_fingerprint(scope, draft)
        key = scope, operation_id
        with self._lock:
            prior = self._operations.get(key)
            if prior is not None:
                if prior[0] != digest:
                    raise EventStoreConflict("event_operation_payload_changed")
                return AppendResult(prior[1], replayed=True)
            now = aware_utc(self._clock.now())
            seq = check_sequence(self._allocator() if self._allocator is not None else self._last_sequence + 1)
            if seq <= self._last_sequence:
                raise EventStoreConflict("event_sequence_not_increasing")
            event = make_event(run_id=scope.run_id, seq=seq, ts=now, type=draft.type, payload=draft.payload)
            self._events.setdefault(scope, []).append(event)
            self._operations[key] = digest, event
            self._last_sequence = seq
            return AppendResult(event)

    def replay(self, scope: RunScope, *, after_seq: int = 0, limit: int = 1000) -> ReplayPage:
        check_scope(scope)
        after_seq, limit = check_page(after_seq, limit)
        with self._lock:
            events = self._events.get(scope, ())
            if after_seq and not any(event.seq == after_seq for event in events):
                raise EventCursorError("event_cursor_unavailable")
            remaining = tuple(event for event in events if event.seq > after_seq)
            page = remaining[:limit]
            return ReplayPage(page, page[-1].seq if page else after_seq, len(remaining) > limit)

    def metadata(self, scope: RunScope) -> tuple[StoredEventMetadata, ...]:
        check_scope(scope)
        with self._lock:
            return tuple(metadata(scope, event) for event in self._events.get(scope, ()))

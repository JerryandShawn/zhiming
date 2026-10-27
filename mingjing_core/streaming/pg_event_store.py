"""Connection-free PG adapter: explicit columns plus injected transaction/allocator/ledger ports."""

from __future__ import annotations

from mingjing_core.timekit.clock import Clock

from .event_models import EventDraft, RunEvent, RunScope, make_event
from .event_store import EventTransaction, TransactionFactory
from .store_contracts import (
    AppendResult,
    EventColumns,
    EventCursorError,
    EventStoreConflict,
    EventStoreError,
    ReplayPage,
    StoredEventMetadata,
)
from .store_serialization import (
    MAX_PAGE,
    aware_utc,
    check_operation_id,
    check_page,
    check_scope,
    check_sequence,
    draft_fingerprint,
    event_row,
    metadata,
    row_event,
)


class PgEventStore:
    def __init__(self, transactions: TransactionFactory, *, clock: Clock, columns: EventColumns | None = None) -> None:
        if columns is not None and not isinstance(columns, EventColumns):
            raise EventStoreError("event_columns_required")
        self._transactions = transactions
        self._clock = clock
        self.columns = columns or EventColumns()

    def append(self, scope: RunScope, draft: EventDraft, *, operation_id: str) -> AppendResult:
        operation_id = check_operation_id(operation_id)
        digest = draft_fingerprint(scope, draft)
        with self._transactions(scope) as transaction:
            transaction.lock_scope(scope)
            transaction.assert_run(scope)
            prior = transaction.find_operation(scope, operation_id)
            if prior is not None:
                event = row_event(scope, prior.row, self.columns)
                if (
                    prior.fingerprint != digest
                    or draft_fingerprint(scope, EventDraft(event.type, event.payload)) != digest
                ):
                    raise EventStoreConflict("event_operation_payload_changed")
                return AppendResult(event, replayed=True)
            previous = check_sequence(transaction.last_sequence(scope), zero=True)
            seq = check_sequence(transaction.next_sequence(scope))
            if seq <= previous:
                raise EventStoreConflict("event_sequence_not_increasing")
            event = make_event(
                run_id=scope.run_id, seq=seq, ts=aware_utc(self._clock.now()), type=draft.type, payload=draft.payload
            )
            transaction.insert_row(self.columns, event_row(scope, event, self.columns))
            transaction.record_operation(scope, operation_id, digest, seq)
            transaction.notify("mj_run", f"{scope.run_id}:{seq}")
            return AppendResult(event)

    def replay(self, scope: RunScope, *, after_seq: int = 0, limit: int = 1000) -> ReplayPage:
        check_scope(scope)
        after_seq, limit = check_page(after_seq, limit)
        with self._transactions(scope) as transaction:
            transaction.assert_run(scope)
            if after_seq:
                cursor = transaction.read_event(scope, after_seq, self.columns)
                if cursor is None:
                    raise EventCursorError("event_cursor_unavailable")
                try:
                    cursor_event = row_event(scope, cursor, self.columns)
                except EventStoreError:
                    raise EventCursorError("event_cursor_unavailable") from None
                if cursor_event.seq != after_seq:
                    raise EventCursorError("event_cursor_unavailable")
            events = self._page(transaction, scope, after_seq, limit + 1)
            page = events[:limit]
            return ReplayPage(page, page[-1].seq if page else after_seq, len(events) > limit)

    def _page(self, transaction: EventTransaction, scope: RunScope, after_seq: int, limit: int) -> tuple[RunEvent, ...]:
        rows = transaction.read_rows(scope, after_seq, limit, self.columns)
        if len(rows) > limit:
            raise EventStoreError("event_page_overflow")
        events = tuple(row_event(scope, row, self.columns) for row in rows)
        if any(event.seq <= after_seq for event in events):
            raise EventStoreError("event_page_cursor_invalid")
        if any(left.seq >= right.seq for left, right in zip(events, events[1:], strict=False)):
            raise EventStoreError("event_page_order_invalid")
        return events

    def metadata(self, scope: RunScope) -> tuple[StoredEventMetadata, ...]:
        check_scope(scope)
        with self._transactions(scope) as transaction:
            transaction.assert_run(scope)
            result, after_seq = [], 0
            while True:
                events = self._page(transaction, scope, after_seq, MAX_PAGE)
                result.extend(metadata(scope, event) for event in events)
                if len(events) < MAX_PAGE:
                    return tuple(result)
                after_seq = events[-1].seq

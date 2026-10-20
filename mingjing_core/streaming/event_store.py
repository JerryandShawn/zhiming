"""Ports only: the host supplies owner authentication, transactions, locks and durable ledgers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Protocol

from .event_models import EventDraft, RunScope
from .store_contracts import AppendResult, EventColumns, ReplayPage, StoredEventMetadata, StoredOperation


class EventStore(Protocol):
    def append(self, scope: RunScope, draft: EventDraft, *, operation_id: str) -> AppendResult:
        """Append atomically, or replay the original event for the same scoped operation."""
        ...

    def replay(self, scope: RunScope, *, after_seq: int = 0, limit: int = 1000) -> ReplayPage:
        """An authenticated route binds the numeric Last-Event-ID to this owner/run."""
        ...

    def metadata(self, scope: RunScope) -> tuple[StoredEventMetadata, ...]:
        """Return private cleanup metadata without text; never delete events here."""
        ...


class SequenceAllocator(Protocol):
    def __call__(self) -> int:
        """Return an increasing bigint; transaction rollback may leave gaps."""
        ...


class EventTransaction(Protocol):
    """All methods run in one host-owned transaction, under an actual scope lock.

    The host must enforce unique(owner,run_id,operation_id) in its ledger. P2 does
    not have that ledger or a sequence default yet. read_rows must order by seq
    and apply owner/run predicates before LIMIT. No implementation connects here.
    """

    def lock_scope(self, scope: RunScope) -> None: ...

    def assert_run(self, scope: RunScope) -> None: ...

    def find_operation(self, scope: RunScope, operation_id: str) -> StoredOperation | None: ...

    def next_sequence(self, scope: RunScope) -> int: ...

    def last_sequence(self, scope: RunScope) -> int: ...

    def insert_row(self, columns: EventColumns, row: Mapping[str, object]) -> None: ...

    def record_operation(self, scope: RunScope, operation_id: str, fingerprint: str, seq: int) -> None: ...

    def notify(self, channel: str, payload: str) -> None: ...

    def read_event(self, scope: RunScope, seq: int, columns: EventColumns) -> Mapping[str, object] | None: ...

    def read_rows(
        self, scope: RunScope, after_seq: int, limit: int, columns: EventColumns
    ) -> Sequence[Mapping[str, object]]: ...


class TransactionFactory(Protocol):
    def __call__(self, scope: RunScope) -> AbstractContextManager[EventTransaction]: ...

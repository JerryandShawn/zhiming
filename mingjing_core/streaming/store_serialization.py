"""Canonical private fingerprints and explicit row mapping, independent of any database connection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from .event_errors import EventValidationError
from .event_models import EventDraft, RunEvent, RunScope, event_data, make_event
from .json_values import thaw_json
from .store_contracts import EventColumns, EventStoreError, StoredEventMetadata

MAX_SEQUENCE = 2**63 - 1
MAX_PAGE = 1000
COMMON = frozenset({"v", "run_id", "seq", "ts"})


def canonical_fingerprint(value: object) -> str:
    raw = json.dumps(thaw_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def draft_fingerprint(scope: RunScope, draft: EventDraft) -> str:
    check_scope(scope)
    if not isinstance(draft, EventDraft):
        raise EventStoreError("event_draft_required")
    return canonical_fingerprint((scope.owner_id, scope.run_id, draft.type, draft.payload))


def check_scope(scope: object) -> None:
    if not isinstance(scope, RunScope):
        raise EventStoreError("event_scope_required")


def check_sequence(value: object, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= MAX_SEQUENCE:
        raise EventStoreError("event_sequence_invalid")
    return value


def check_page(after_seq: object, limit: object) -> tuple[int, int]:
    after = check_sequence(after_seq, zero=True)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise EventStoreError("event_page_limit_invalid")
    return after, limit


def check_operation_id(operation_id: object) -> str:
    if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 256:
        raise EventStoreError("event_operation_id_required")
    return operation_id


def aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EventStoreError("event_timestamp_must_be_aware")
    return value.astimezone(UTC)


def event_row(scope: RunScope, event: RunEvent, columns: EventColumns) -> dict[str, object]:
    if event.run_id != scope.run_id:
        raise EventStoreError("event_scope_mismatch")
    return {
        columns.owner: scope.owner_id,
        columns.run_id: event.run_id,
        columns.seq: event.seq,
        columns.type: event.type,
        columns.data: event_data(event),
        columns.created_at: event.ts,
    }


def row_event(scope: RunScope, row: Mapping[str, object], columns: EventColumns) -> RunEvent:
    if not isinstance(row, Mapping) or set(row) != {getattr(columns, key) for key in columns.__dataclass_fields__}:
        raise EventStoreError("event_row_shape_invalid")
    if row[columns.owner] != scope.owner_id or row[columns.run_id] != scope.run_id:
        raise EventStoreError("event_scope_mismatch")
    wire = row[columns.data]
    if not isinstance(wire, Mapping) or not wire.keys() >= COMMON:
        raise EventStoreError("event_wire_shape_invalid")
    if type(wire["v"]) is not int or wire["v"] != 1 or type(wire["seq"]) is not int:
        raise EventStoreError("event_wire_identity_invalid")
    seq = check_sequence(row[columns.seq])
    if wire["run_id"] != scope.run_id or wire["seq"] != seq:
        raise EventStoreError("event_wire_identity_invalid")
    if not isinstance(wire["ts"], str):
        raise EventStoreError("event_wire_timestamp_invalid")
    try:
        event = make_event(
            run_id=scope.run_id,
            seq=seq,
            ts=aware_utc(row[columns.created_at]),
            type=row[columns.type],
            payload={key: value for key, value in wire.items() if key not in COMMON},
        )
    except EventValidationError:
        raise EventStoreError("event_row_payload_invalid") from None
    if event_data(event) != thaw_json(wire):
        raise EventStoreError("event_wire_mismatch")
    return event


def metadata(scope: RunScope, event: RunEvent) -> StoredEventMetadata:
    digest = canonical_fingerprint((event.type, event_data(event)))
    return StoredEventMetadata(scope, event.seq, event.type, event.ts, digest)

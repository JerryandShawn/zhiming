"""Strict row projections and scoped retry races; injected ports do not establish real PG correctness."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any

import pytest

from mingjing_core.streaming.event_models import EventDraft, RunScope
from mingjing_core.streaming.memory_event_store import MemoryEventStore
from mingjing_core.streaming.pg_event_store import PgEventStore
from mingjing_core.streaming.resume import replay_after_header
from mingjing_core.streaming.store_contracts import (
    EventCursorError,
    EventStoreConflict,
    EventStoreError,
    StoredOperation,
)
from mingjing_core.streaming.store_serialization import MAX_SEQUENCE, draft_fingerprint, event_row, row_event
from mingjing_core.timekit.clock import FrozenClock
from tests.v4.streaming.coverage_support_acceptance_mod import AT, COLUMNS, SCOPE, RowPort, event, row


@pytest.mark.parametrize("value", [None, {}, "scope"])
def test_public_stores_reject_unscoped_reads_and_non_draft_writes(value: object) -> None:
    store = MemoryEventStore(clock=FrozenClock(AT))
    with pytest.raises(EventStoreError):
        store.replay(value)
    with pytest.raises(EventStoreError):
        store.append(SCOPE, value, operation_id="operation")


@pytest.mark.parametrize("columns", [False, {}, "payload"])
def test_pg_adapter_requires_an_explicit_column_mapping_object(columns: object) -> None:
    with pytest.raises(EventStoreError):
        PgEventStore(RowPort(), clock=FrozenClock(AT), columns=columns)


@pytest.mark.parametrize(
    "mutation",
    [
        {"payload": []},
        {"payload": {"v": 1}},
        {"payload": {"v": 1, "run_id": SCOPE.run_id, "seq": 1, "ts": 123, "text": "虚构"}},
        {"kind": "unknown"},
        {"payload": {"v": 1, "run_id": SCOPE.run_id, "seq": 1, "ts": "bad-time", "text": "虚构"}},
    ],
)
def test_row_projection_rejects_malformed_wire_without_publishing_partial_history(mutation: dict[str, Any]) -> None:
    value = row() | mutation
    with pytest.raises(EventStoreError):
        row_event(SCOPE, value, COLUMNS)
    with pytest.raises(EventStoreError):
        PgEventStore(RowPort((value,)), clock=FrozenClock(AT)).replay(SCOPE)


def test_row_projection_requires_exact_columns_and_rejects_payload_model_failure() -> None:
    for value in (row() | {"extra": "private"}, {key: value for key, value in row().items() if key != "owner"}):
        with pytest.raises(EventStoreError):
            row_event(SCOPE, value, COLUMNS)
    value = row()
    value["payload"]["text"] = 17
    with pytest.raises(EventStoreError, match="event_row_payload_invalid"):
        row_event(SCOPE, value, COLUMNS)
    with pytest.raises(EventStoreError):
        event_row(RunScope(SCOPE.owner_id, "other-run"), event("text_delta"), COLUMNS)


def test_pg_cursor_with_valid_but_wrong_sequence_is_as_unavailable_as_unknown() -> None:
    store = PgEventStore(RowPort(cursor=row(8)), clock=FrozenClock(AT))
    with pytest.raises(EventCursorError, match="^event_cursor_unavailable$"):
        replay_after_header(store, SCOPE, "7")
    assert store.columns == COLUMNS


@pytest.mark.parametrize("prior_kind", ["wrong-fingerprint", "wire-body-changed", "foreign-owner"])
def test_pg_operation_ledger_cannot_authorize_a_changed_or_foreign_original(prior_kind: str) -> None:
    draft = EventDraft("text_delta", {"text": "虚构行"})
    value = row()
    digest = draft_fingerprint(SCOPE, draft)
    if prior_kind == "wrong-fingerprint":
        digest = "0" * 64
    elif prior_kind == "wire-body-changed":
        value["payload"]["text"] = "虚构篡改"
    else:
        value["owner"] = "other-owner"
    port = RowPort(prior=StoredOperation(digest, value))
    with pytest.raises(EventStoreError):
        PgEventStore(port, clock=FrozenClock(AT)).append(SCOPE, draft, operation_id="same-operation")
    assert "allocate" not in port.calls and "notify" not in port.calls


@pytest.mark.parametrize("seq", [True, -1, 0, MAX_SEQUENCE + 1])
def test_pg_allocator_bad_value_never_enters_row_or_operation_ledger(seq: object) -> None:
    port = RowPort(allocated=seq)
    with pytest.raises(EventStoreError):
        PgEventStore(port, clock=FrozenClock(AT)).append(
            SCOPE, EventDraft("text_delta", {"text": "虚构"}), operation_id="op"
        )
    assert "insert" not in port.calls and "record" not in port.calls and "notify" not in port.calls


def test_bigint_last_identity_is_usable_but_overflow_does_not_corrupt_replay() -> None:
    store = MemoryEventStore(clock=FrozenClock(AT), allocator=iter((MAX_SEQUENCE, MAX_SEQUENCE + 1)).__next__)
    first = store.append(SCOPE, EventDraft("text_delta", {"text": "虚构最后一行"}), operation_id="last")
    with pytest.raises(EventStoreError):
        store.append(SCOPE, EventDraft("text_delta", {"text": "不得入库"}), operation_id="overflow")
    assert replay_after_header(store, SCOPE, str(MAX_SEQUENCE)).events == ()
    assert store.replay(SCOPE).events == (first.event,)
    assert store.append(SCOPE, EventDraft("text_delta", {"text": "虚构最后一行"}), operation_id="last").replayed


def test_competing_payloads_under_one_operation_publish_one_winner_without_partial_second_event() -> None:
    store = MemoryEventStore(clock=FrozenClock(AT))

    def attempt(text: str) -> object:
        try:
            return store.append(SCOPE, EventDraft("text_delta", {"text": text}), operation_id="contended")
        except EventStoreConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(attempt, ("虚构竞争甲", "虚构竞争乙")))
    assert sum(result is not None for result in results) == 1
    persisted = store.replay(SCOPE).events
    assert len(persisted) == 1 and persisted[0].seq == 1
    winner = persisted[0].payload["text"]
    assert store.append(SCOPE, EventDraft("text_delta", {"text": winner}), operation_id="contended").replayed


def test_parallel_identical_operation_names_are_independent_for_each_owner_and_run() -> None:
    scopes = (SCOPE, RunScope(SCOPE.owner_id, "other-run"), RunScope("other-owner", SCOPE.run_id))
    store = MemoryEventStore(clock=FrozenClock(AT))

    def append(index: int) -> object:
        scope = scopes[index % 3]
        return store.append(
            scope, EventDraft("text_delta", {"text": scope.owner_id + scope.run_id}), operation_id="shared"
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(append, range(30)))
    assert sum(not result.replayed for result in results) == 3
    assert len({store.replay(scope).events[0].seq for scope in scopes}) == 3
    for scope in scopes:
        assert len(store.replay(scope).events) == 1
        foreign = next(other for other in scopes if other != scope)
        cursor = str(store.replay(foreign).events[0].seq)
        with pytest.raises(EventCursorError):
            replay_after_header(store, scope, cursor)


def test_changed_exported_wire_does_not_modify_immutable_retry_history() -> None:
    value = row()
    original = row_event(SCOPE, value, COLUMNS)
    exported = event_row(SCOPE, original, COLUMNS)
    exported["payload"]["text"] = "虚构外部改写"
    copied = deepcopy(value)
    assert event_row(SCOPE, original, COLUMNS)["payload"]["text"] == "虚构行"
    assert row_event(SCOPE, copied, COLUMNS) == original

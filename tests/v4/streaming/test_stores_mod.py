"""Offline row-port tests; no PG connection or durable concurrency claim is made."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from random import Random
from threading import RLock

import pytest

from mingjing_core.streaming.event_models import EventDraft, RunScope, event_data, make_event
from mingjing_core.streaming.memory_event_store import MemoryEventStore
from mingjing_core.streaming.pg_event_store import PgEventStore
from mingjing_core.streaming.store_contracts import (
    EventColumns,
    EventCursorError,
    EventStoreConflict,
    EventStoreError,
    StoredOperation,
)
from mingjing_core.streaming.store_serialization import event_row
from mingjing_core.timekit.clock import FrozenClock

NOW = datetime(2026, 10, 21, 0, tzinfo=UTC)
SCOPE = RunScope("owner-a", "run-a")
OTHER = RunScope("owner-b", "run-b")
SAME_OWNER = RunScope("owner-a", "run-c")


def draft(text="合成私有正文", kind="text_delta"):
    return EventDraft(kind, {"text": text})


class FakeDatabase:
    def __init__(self):
        self.rows, self.operations, self.calls = {}, {}, []
        self.sequence = 0
        self.fail = None
        self.lock = RLock()

    @contextmanager
    def __call__(self, scope):
        with self.lock:
            before = deepcopy((self.rows, self.operations))
            self.calls.append("begin")
            try:
                yield FakeTransaction(self)
            except Exception:
                self.rows, self.operations = before
                self.calls.append("rollback")
                raise
            else:
                self.calls.append("commit")


class FakeTransaction:
    def __init__(self, database):
        self.db = database

    def lock_scope(self, scope):
        self.db.calls.append("lock")

    def assert_run(self, scope):
        self.db.calls.append("assert")
        if scope not in (SCOPE, OTHER, SAME_OWNER):
            raise EventStoreError("run_unavailable")

    def find_operation(self, scope, operation_id):
        self.db.calls.append("find")
        prior = self.db.operations.get((scope, operation_id))
        return StoredOperation(prior[0], deepcopy(self.db.rows[scope, prior[1]])) if prior else None

    def last_sequence(self, scope):
        self.db.calls.append("last")
        return max((seq for item_scope, seq in self.db.rows if item_scope == scope), default=0)

    def next_sequence(self, scope):
        self.db.calls.append("allocate")
        self.db.sequence += 7
        return self.db.sequence

    def insert_row(self, columns, row):
        self.db.calls.append("insert")
        if self.db.fail == "insert":
            raise EventStoreError("synthetic_insert_failure")
        scope = RunScope(row[columns.owner], row[columns.run_id])
        self.db.rows[scope, row[columns.seq]] = deepcopy(row)

    def record_operation(self, scope, operation_id, fingerprint, seq):
        self.db.calls.append("record")
        if self.db.fail == "record":
            raise EventStoreError("synthetic_record_failure")
        self.db.operations[scope, operation_id] = fingerprint, seq

    def notify(self, channel, payload):
        self.db.calls.append("notify")
        assert channel == "mj_run" and payload.split(":")[-1].isdigit()
        if self.db.fail == "notify":
            raise EventStoreError("synthetic_notify_failure")

    def read_event(self, scope, seq, columns):
        return deepcopy(self.db.rows.get((scope, seq)))

    def read_rows(self, scope, after_seq, limit, columns):
        keys = sorted((key for key in self.db.rows if key[0] == scope and key[1] > after_seq), key=lambda key: key[1])
        return [deepcopy(self.db.rows[key]) for key in keys[:limit]]


@pytest.fixture(params=["memory", "pg-port"])
def store(request):
    clock = FrozenClock(NOW)
    return (
        MemoryEventStore(clock=clock) if request.param == "memory" else PgEventStore(FakeDatabase(), clock=clock),
        clock,
    )


def test_operation_replay_retains_original_sequence_and_timestamp(store):
    log, clock = store
    first = log.append(SCOPE, draft(), operation_id="same")
    clock.advance(timedelta(hours=1))
    again = log.append(SCOPE, draft(), operation_id="same")
    assert not first.replayed and again.replayed and again.event == first.event
    assert len(log.replay(SCOPE).events) == 1
    assert event_data(again.event)["ts"].endswith("+08:00")


def test_changed_operation_payload_is_conflict_and_scope_isolated(store):
    log, _ = store
    log.append(SCOPE, draft("合成甲"), operation_id="same")
    with pytest.raises(EventStoreConflict):
        log.append(SCOPE, draft("合成乙"), operation_id="same")
    assert not log.append(OTHER, draft("合成乙"), operation_id="same").replayed
    assert log.replay(SCOPE).events[0].payload["text"] == "合成甲"


def test_foreign_unknown_cursor_and_cross_run_do_not_return_text(store):
    log, _ = store
    first = log.append(SCOPE, draft(), operation_id="a").event
    log.append(OTHER, draft("另一位合成用户"), operation_id="b")
    log.append(SAME_OWNER, draft("同owner另一run"), operation_id="c")
    for scope in (OTHER, SAME_OWNER):
        with pytest.raises(EventCursorError, match="event_cursor_unavailable"):
            log.replay(scope, after_seq=first.seq)
    with pytest.raises(EventCursorError):
        log.replay(SCOPE, after_seq=2**62)


def test_page_resume_has_no_contiguous_sequence_assumption(store):
    log, _ = store
    events = [log.append(SCOPE, draft(str(index)), operation_id=str(index)).event for index in range(5)]
    first = log.replay(SCOPE, limit=2)
    second = log.replay(SCOPE, after_seq=first.next_seq, limit=2)
    third = log.replay(SCOPE, after_seq=second.next_seq, limit=2)
    assert first.events + second.events + third.events == tuple(events)
    assert first.has_more and second.has_more and not third.has_more
    empty = log.replay(SCOPE, after_seq=third.next_seq)
    assert empty.events == () and empty.next_seq == third.next_seq and not empty.has_more


def test_metadata_and_public_repr_do_not_echo_payload(store):
    log, _ = store
    result = log.append(SCOPE, draft("合成秘密正文-ABCD"), operation_id="private")
    metadata = log.metadata(SCOPE)
    assert len(metadata) == 1 and metadata[0].scope == SCOPE and metadata[0].seq == result.event.seq
    assert "合成秘密正文" not in repr((metadata, result, log.replay(SCOPE)))
    assert "owner" not in event_data(result.event)


@pytest.mark.parametrize("after,limit", [(True, 1), (-1, 1), (1.0, 1), (0, True), (0, 0), (0, 1001)])
def test_typed_cursor_and_page_bounds(store, after, limit):
    log, _ = store
    with pytest.raises(EventStoreError):
        log.replay(SCOPE, after_seq=after, limit=limit)


@pytest.mark.parametrize("operation", ["", " ", None, 1, "x" * 257])
def test_operation_id_is_mandatory(store, operation):
    log, _ = store
    with pytest.raises(EventStoreError):
        log.append(SCOPE, draft(), operation_id=operation)


@pytest.mark.parametrize("failed_stage", ["insert", "record", "notify"])
def test_pg_port_transaction_rolls_back_event_ledger_and_notification_intent(failed_stage):
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    database.fail = failed_stage
    with pytest.raises(EventStoreError):
        log.append(SCOPE, draft(), operation_id="atomic")
    assert not database.rows and not database.operations and database.calls[-1] == "rollback"
    database.fail = None
    retry = log.append(SCOPE, draft(), operation_id="atomic")
    assert retry.event.seq == 14 and not retry.replayed


def test_pg_explicit_p2_columns_and_transaction_call_order():
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    log.append(SCOPE, draft(), operation_id="a")
    assert database.calls == [
        "begin",
        "lock",
        "assert",
        "find",
        "last",
        "allocate",
        "insert",
        "record",
        "notify",
        "commit",
    ]
    row = next(iter(database.rows.values()))
    assert set(row) == {"owner", "run_id", "seq", "kind", "payload", "created_at"}
    assert row["payload"]["seq"] == row["seq"] and row["payload"]["v"] == 1


def test_pg_alternate_type_data_mapping_is_an_explicit_choice():
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW), columns=EventColumns(type="type", data="data"))
    expected = log.append(SCOPE, draft(), operation_id="alternate").event
    assert "type" in next(iter(database.rows.values()))
    assert log.replay(SCOPE).events == (expected,)


@pytest.mark.parametrize("column", ["bad-name", "payload;delete", "", 1, "seq"])
def test_column_names_are_typed_identifiers_and_distinct(column):
    with pytest.raises(EventStoreError):
        EventColumns(data=column)


@pytest.mark.parametrize(
    "field,value", [("owner", "other"), ("run_id", "other"), ("seq", True), ("created_at", NOW.replace(tzinfo=None))]
)
def test_pg_replay_revalidates_every_row(field, value):
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    event = log.append(SCOPE, draft(), operation_id="valid").event
    database.rows[SCOPE, event.seq][field] = value
    with pytest.raises(ValueError):
        log.replay(SCOPE)


@pytest.mark.parametrize(
    "field,value",
    [
        ("v", True),
        ("seq", False),
        ("seq", 99),
        ("run_id", "other"),
        ("ts", "2026-10-21T00:00:00+00:00"),
        ("unexpected", "x"),
    ],
)
def test_pg_replay_cross_checks_wire_against_private_row(field, value):
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    event = log.append(SCOPE, draft(), operation_id="valid").event
    database.rows[SCOPE, event.seq]["payload"][field] = value
    with pytest.raises(ValueError):
        log.replay(SCOPE)


def test_memory_lock_serializes_parallel_append_and_duplicate_operations():
    log = MemoryEventStore(clock=FrozenClock(NOW))
    with ThreadPoolExecutor(max_workers=4) as workers:
        results = list(
            workers.map(lambda i: log.append(SCOPE, draft(str(i % 20)), operation_id=str(i % 20)), range(200))
        )
    assert len(log.replay(SCOPE).events) == 20
    assert sum(not item.replayed for item in results) == 20
    assert [item.seq for item in log.replay(SCOPE).events] == list(range(1, 21))


@pytest.mark.parametrize("invalid_sequence", [True, -1, 0, 1.5, 2**63])
def test_memory_allocator_rejects_invalid_bigint(invalid_sequence):
    log = MemoryEventStore(clock=FrozenClock(NOW), allocator=lambda: invalid_sequence)
    with pytest.raises(EventStoreError):
        log.append(SCOPE, draft(), operation_id="bad")
    assert log.replay(SCOPE).events == ()


def test_pg_allocator_cannot_move_backwards():
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    log.append(SCOPE, draft(), operation_id="a")
    database.sequence = 0
    with pytest.raises(EventStoreConflict):
        log.append(SCOPE, draft(), operation_id="b")
    assert len(log.replay(SCOPE).events) == 1


@pytest.mark.parametrize("mode", ["reverse", "duplicate", "overflow", "old"])
def test_pg_malformed_page_is_rejected_without_partial_result(monkeypatch, mode):
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    events = [log.append(SCOPE, draft(), operation_id=str(index)).event for index in range(3)]
    rows = [deepcopy(database.rows[SCOPE, event.seq]) for event in events]
    invalid = {"reverse": rows[::-1], "duplicate": rows[:1] * 2, "overflow": rows * 2, "old": rows[:1]}
    monkeypatch.setattr(FakeTransaction, "read_rows", lambda *args: invalid[mode])
    with pytest.raises(EventStoreError):
        log.replay(SCOPE, after_seq=events[0].seq if mode == "old" else 0, limit=2)


def test_pg_foreign_cursor_row_has_same_public_error_as_unknown(monkeypatch):
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    event = log.append(SCOPE, draft(), operation_id="a").event
    foreign = deepcopy(database.rows[SCOPE, event.seq])
    foreign["owner"] = "other"
    monkeypatch.setattr(FakeTransaction, "read_event", lambda *args: foreign)
    with pytest.raises(EventCursorError, match="^event_cursor_unavailable$"):
        log.replay(SCOPE, after_seq=event.seq)


def test_nested_payload_and_output_copies_cannot_change_stored_history(store):
    log, _ = store
    body = {
        "call_id": "c1",
        "name": "synthetic",
        "summary": "合成摘要",
        "ok": True,
        "receipt": {"write_status": "saved", "affected_ids": ["before"]},
    }
    item = EventDraft("tool_result", body)
    result = log.append(SCOPE, item, operation_id="nested")
    body["receipt"]["affected_ids"][0] = "changed"
    wire = event_data(result.event)
    wire["receipt"]["affected_ids"][0] = "changed-again"
    assert event_data(log.replay(SCOPE).events[0])["receipt"]["affected_ids"] == ["before"]


def test_pg_replay_operation_does_not_allocate_or_notify_twice():
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    log.append(SCOPE, draft(), operation_id="a")
    database.calls.clear()
    assert log.append(SCOPE, draft(), operation_id="a").replayed
    assert database.calls == ["begin", "lock", "assert", "find", "commit"]


def test_pg_metadata_pages_across_one_thousand_rows_without_text():
    database = FakeDatabase()
    log = PgEventStore(database, clock=FrozenClock(NOW))
    for index in range(1003):
        event = make_event(
            run_id=SCOPE.run_id, seq=(index + 1) * 7, ts=NOW, type="text_delta", payload={"text": "合成私有正文"}
        )
        database.rows[SCOPE, event.seq] = event_row(SCOPE, event, log.columns)
    result = log.metadata(SCOPE)
    assert len(result) == 1003 and result[-1].seq == 7021
    assert all(item.scope == SCOPE and item.type == "text_delta" for item in result)
    assert "合成私有正文" not in repr(result)


@pytest.mark.parametrize("seed", range(100))
def test_scoped_replay_property_with_random_gaps_retries_and_page_sizes(seed):
    rng = Random(30261021 + seed)
    sequence = 0

    def allocate():
        nonlocal sequence
        sequence += rng.randint(1, 20)
        return sequence

    log = MemoryEventStore(clock=FrozenClock(NOW), allocator=allocate)
    expected = {SCOPE: [], OTHER: [], SAME_OWNER: []}
    for index in range(40):
        scope = rng.choice(tuple(expected))
        item = draft(str(index))
        event = log.append(scope, item, operation_id=str(index)).event
        expected[scope].append(event)
        assert log.append(scope, item, operation_id=str(index)).replayed
    for scope, events in expected.items():
        seen, cursor = [], 0
        while True:
            page = log.replay(scope, after_seq=cursor, limit=rng.randint(1, 7))
            seen.extend(page.events)
            cursor = page.next_seq
            if not page.has_more:
                break
        assert seen == events

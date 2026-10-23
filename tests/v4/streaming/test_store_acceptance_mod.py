"""Store scope/cursor oracle; PG tests inject port faults and do not claim a database integration."""

import copy
from datetime import UTC, datetime, timedelta
from random import Random

import pytest

from mingjing_core.streaming.event_models import EventDraft, RunScope
from mingjing_core.streaming.memory_event_store import MemoryEventStore
from mingjing_core.streaming.pg_event_store import PgEventStore
from mingjing_core.streaming.store_contracts import (
    EventColumns,
    EventCursorError,
    EventStoreConflict,
    EventStoreError,
)
from mingjing_core.timekit.clock import FrozenClock

AT = datetime(2026, 10, 21, tzinfo=UTC)
SCOPE = RunScope("owner", "run-a")
DEFAULT_COLUMNS = EventColumns()


def draft(text="合成文本"):
    return EventDraft("text_delta", {"text": text})


def test_scoped_operation_replay_retains_original_timestamp_without_consuming_sequence():
    clock = FrozenClock(AT)
    store = MemoryEventStore(clock=clock)
    first = store.append(SCOPE, draft(), operation_id="stable")
    clock.advance(timedelta(days=1))
    replay = store.append(SCOPE, draft(), operation_id="stable")
    assert replay.replayed and replay.event == first.event and replay.event.ts == AT
    second = store.append(SCOPE, draft("后续合成文本"), operation_id="next")
    assert second.event.seq == first.event.seq + 1
    with pytest.raises(EventStoreConflict):
        store.append(SCOPE, draft("相同操作号却改正文"), operation_id="stable")
    assert len(store.replay(SCOPE).events) == 2


def test_global_bigserial_gaps_and_pagination_do_not_assume_consecutive_run_sequences():
    allocation = iter([2, 5, 9, 20, 29])
    store = MemoryEventStore(clock=FrozenClock(AT), allocator=lambda: next(allocation))
    other = RunScope("other-owner", "same-visible-run")
    first = store.append(SCOPE, draft("一"), operation_id="one").event
    foreign = store.append(other, draft("其他人的正文"), operation_id="foreign").event
    for identity in ("two", "three", "four"):
        store.append(SCOPE, draft(identity), operation_id=identity)
    page = store.replay(SCOPE, after_seq=first.seq, limit=2)
    assert [event.seq for event in page.events] == [9, 20]
    assert page.next_seq == 20 and page.has_more
    last = store.replay(SCOPE, after_seq=page.next_seq, limit=2)
    assert [event.seq for event in last.events] == [29] and not last.has_more
    assert not store.replay(SCOPE, after_seq=29).events
    with pytest.raises(EventCursorError):
        store.replay(SCOPE, after_seq=foreign.seq)


@pytest.mark.parametrize("foreign", [RunScope("other", "run-a"), RunScope("owner", "run-b")])
def test_owner_and_run_isolation_apply_to_rows_cursors_and_operation_ids(foreign):
    store = MemoryEventStore(clock=FrozenClock(AT))
    mine = store.append(SCOPE, draft("我的正文"), operation_id="same-operation").event
    theirs = store.append(foreign, draft("别人的正文"), operation_id="same-operation").event
    assert [event.seq for event in store.replay(SCOPE).events] == [mine.seq]
    assert [event.seq for event in store.replay(foreign).events] == [theirs.seq]
    with pytest.raises(EventCursorError) as first:
        store.replay(SCOPE, after_seq=theirs.seq)
    with pytest.raises(EventCursorError) as second:
        store.replay(SCOPE, after_seq=999999)
    assert str(first.value) == str(second.value)
    assert "别人的正文" not in repr(store.metadata(foreign))


@pytest.mark.parametrize(
    "after,limit",
    [(True, 1), (-1, 1), (1.5, 1), ("0", 1), (0, 0), (0, True), (0, 1001)],
)
def test_cursor_and_page_size_types_are_strict(after, limit):
    with pytest.raises(EventStoreError):
        MemoryEventStore(clock=FrozenClock(AT)).replay(SCOPE, after_seq=after, limit=limit)


@pytest.mark.parametrize("operation", ["", " ", None, 1])
def test_operation_identity_is_required(operation):
    with pytest.raises(EventStoreError):
        MemoryEventStore(clock=FrozenClock(AT)).append(SCOPE, draft(), operation_id=operation)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, 2**63])
def test_sequence_allocator_cannot_emit_invalid_or_reused_identity(bad):
    with pytest.raises(EventStoreError):
        MemoryEventStore(clock=FrozenClock(AT), allocator=lambda: bad).append(SCOPE, draft(), operation_id="bad")
    allocation = iter([5, 5])
    store = MemoryEventStore(clock=FrozenClock(AT), allocator=lambda: next(allocation))
    store.append(SCOPE, draft(), operation_id="first")
    with pytest.raises(EventStoreConflict):
        store.append(SCOPE, draft(), operation_id="second")


@pytest.mark.parametrize("seed", range(20))
def test_random_scoped_append_replay_roundtrip_preserves_every_original_exactly_once(
    seed,
):
    rng, clock = Random(33071 + seed), FrozenClock(AT)
    store = MemoryEventStore(clock=clock)
    scopes = (SCOPE, RunScope("owner", "run-b"), RunScope("other", "run-a"))
    expected = {scope: [] for scope in scopes}
    for step in range(50):
        clock.advance(timedelta(milliseconds=rng.randrange(200)))
        scope = rng.choice(scopes)
        if expected[scope] and rng.randrange(3) == 0:
            operation, text, original = rng.choice(expected[scope])
            result = store.append(scope, draft(text), operation_id=operation)
            assert result.replayed and result.event == original
        else:
            operation, text = f"operation-{step}", f"合成-{seed}-{step}-🌙\n结束"
            original = store.append(scope, draft(text), operation_id=operation).event
            expected[scope].append((operation, text, original))
    for scope in scopes:
        found, after = [], 0
        while True:
            page = store.replay(scope, after_seq=after, limit=3)
            found.extend(page.events)
            after = page.next_seq
            if not page.has_more:
                break
        assert found == [original for _, _, original in expected[scope]]
        assert len({item.seq for item in found}) == len(found)


def row(seq, *, scope=SCOPE, columns=DEFAULT_COLUMNS):
    return {
        columns.owner: scope.owner_id,
        columns.run_id: scope.run_id,
        columns.seq: seq,
        columns.type: "text_delta",
        columns.created_at: AT,
        columns.data: {
            "v": 1,
            "run_id": scope.run_id,
            "seq": seq,
            "ts": "2026-10-21T08:00:00+08:00",
            "text": f"合成行-{seq}",
        },
    }


class ReadPort:
    """Deliberately does not filter: adapter must still validate returned identities."""

    def __init__(self, rows, cursor=None):
        self.rows, self.cursor, self.calls = rows, cursor, []

    def __call__(self, scope):
        self.calls.append(("transaction", scope))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def assert_run(self, scope):
        self.calls.append(("authorize", scope))

    def read_event(self, scope, seq, columns):
        self.calls.append(("cursor", scope, seq, columns))
        return self.cursor

    def read_rows(self, scope, after_seq, limit, columns):
        self.calls.append(("rows", scope, after_seq, limit, columns))
        return self.rows


@pytest.mark.parametrize("foreign", [RunScope("other", "run-a"), RunScope("owner", "run-b")])
def test_pg_port_cannot_return_foreign_rows_even_if_its_query_filter_is_wrong(foreign):
    port = ReadPort((row(1, scope=foreign),))
    with pytest.raises(EventStoreError):
        PgEventStore(port, clock=FrozenClock(AT)).replay(SCOPE)
    assert port.calls[0:2] == [("transaction", SCOPE), ("authorize", SCOPE)]


@pytest.mark.parametrize("rows", [(row(2), row(1)), (row(1), row(1))])
def test_pg_port_rejects_unsorted_and_duplicate_sequences(rows):
    with pytest.raises(EventStoreError):
        PgEventStore(ReadPort(rows), clock=FrozenClock(AT)).replay(SCOPE)


def test_pg_port_rejects_foreign_cursor_without_exposing_owner_or_data():
    foreign = row(1, scope=RunScope("secret-owner", "secret-run"))
    with pytest.raises(EventCursorError) as caught:
        PgEventStore(ReadPort((), foreign), clock=FrozenClock(AT)).replay(SCOPE, after_seq=1)
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("columns", [EventColumns(), EventColumns(type="type", data="data")])
def test_pg_column_mapping_is_explicit_and_preserves_core_run_events_wire_shape(
    columns,
):
    original = row(7, columns=columns)
    port = ReadPort((copy.deepcopy(original),))
    store = PgEventStore(port, clock=FrozenClock(AT), columns=columns)
    page = store.replay(SCOPE)
    assert len(page.events) == 1 and page.events[0].seq == 7
    assert page.events[0].payload["text"] == "合成行-7"
    assert port.rows == (original,)
    assert port.calls[-1][-1] == columns

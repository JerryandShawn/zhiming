"""Header syntax and source cursor ownership are separate, mandatory gates."""

from datetime import UTC, datetime

import pytest

from mingjing_core.streaming.event_models import EventDraft, RunScope
from mingjing_core.streaming.memory_event_store import MemoryEventStore
from mingjing_core.streaming.resume import parse_last_event_id, replay_after_header
from mingjing_core.streaming.store_contracts import EventCursorError
from mingjing_core.timekit.clock import FrozenClock


@pytest.mark.parametrize("header", ["", "01", "00", "+1", "-1", "1.0", "1e3", " 1", "1\n", "１２", True, "9" * 100])
def test_bad_headers_are_not_coerced(header):
    with pytest.raises(EventCursorError, match="unavailable"):
        parse_last_event_id(header)


def test_signed_bigint_boundaries():
    assert parse_last_event_id(None) == 0
    assert parse_last_event_id("0") == 0
    assert parse_last_event_id(str(2**63 - 1)) == 2**63 - 1
    with pytest.raises(EventCursorError):
        parse_last_event_id(str(2**63))


def test_numeric_cursor_does_not_grant_scope_authority():
    store = MemoryEventStore(clock=FrozenClock(datetime(2026, 10, 17, tzinfo=UTC)))
    actual, other = RunScope("owner", "run1"), RunScope("other", "run1")
    event = store.append(actual, EventDraft("text_delta", {"text": "合成"}), operation_id="op").event
    with pytest.raises(EventCursorError):
        replay_after_header(store, other, str(event.seq))
    assert not replay_after_header(store, actual, str(event.seq)).events

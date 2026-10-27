"""Canonical Last-Event-ID parsing never guesses an unavailable or foreign cursor."""

import re

from .event_models import RunScope
from .event_store import EventStore
from .store_contracts import EventCursorError, ReplayPage
from .store_serialization import MAX_SEQUENCE


def parse_last_event_id(value: str | None) -> int:
    if value is None:
        return 0
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]{0,18}", value):
        raise EventCursorError("event_cursor_unavailable")
    sequence = int(value)
    if sequence > MAX_SEQUENCE:
        raise EventCursorError("event_cursor_unavailable")
    return sequence


def replay_after_header(
    store: EventStore, scope: RunScope, last_event_id: str | None, *, limit: int = 1000
) -> ReplayPage:
    return store.replay(scope, after_seq=parse_last_event_id(last_event_id), limit=limit)

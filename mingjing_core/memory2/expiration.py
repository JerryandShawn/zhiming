"""Resolve conservative archive deadlines without interpreting relative language twice."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _boundary(value: object, zone: ZoneInfo, *, end_of_day: bool) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        if len(value) == 10:
            day = date.fromisoformat(value)
            if end_of_day:
                day += timedelta(days=1)
            return datetime.combine(day, time.min, zone).astimezone(UTC)
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return None
        return instant.astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def archive_deadline(fact: dict[str, Any]) -> datetime | None:
    """Date-only events last through the owner's local day; instants are exclusive ends.

    A present but malformed endpoint blocks archival rather than silently shortening
    an event. Ordinary goals containing dates are not inferred to be expiring events.
    """
    # A closed single-slot predecessor remains active for historical queries.
    if fact.get("superseded_by"):
        return None
    try:
        zone = ZoneInfo(fact.get("owner_timezone", "Asia/Shanghai"))
    except (TypeError, ValueError, ZoneInfoNotFoundError):
        return None
    deadlines = []
    if fact.get("valid_to") is not None:
        until = _boundary(fact["valid_to"], zone, end_of_day=False)
        if until is None:
            return None
        deadlines.append(until)
    if fact.get("kind") == "event" or fact.get("requested_kind") == "event":
        field = "event_end" if fact.get("event_end") is not None else "event_at"
        event_end = _boundary(fact.get(field), zone, end_of_day=True)
        if event_end is None:
            return None
        start = _boundary(fact.get("event_at"), zone, end_of_day=False)
        if start is None or event_end < start:
            return None
        deadlines.append(event_end)
    return min(deadlines) if deadlines else None

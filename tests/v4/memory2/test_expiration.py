"""Absolute dates use the owner's timezone and never guess malformed or relative ends."""

from datetime import UTC, datetime

import pytest

from mingjing_core.memory2.expiration import archive_deadline


@pytest.mark.parametrize(
    "fields,expected",
    [
        ({"event_at": "2026-10-23"}, "2026-10-23T16:00:00+00:00"),
        ({"event_at": "2026-10-23T10:00:00+08:00"}, "2026-10-23T02:00:00+00:00"),
        (
            {"event_at": "2026-10-23", "event_end": "2026-10-25"},
            "2026-10-25T16:00:00+00:00",
        ),
        (
            {"event_at": "2026-10-23", "event_end": "2026-10-25T12:00:00+08:00"},
            "2026-10-25T04:00:00+00:00",
        ),
        (
            {"event_at": "2026-10-23", "valid_to": "2026-10-23T12:00:00+08:00"},
            "2026-10-23T04:00:00+00:00",
        ),
        (
            {"event_at": "2026-10-23", "owner_timezone": "UTC"},
            "2026-10-24T00:00:00+00:00",
        ),
        (
            {"event_at": "2026-11-01", "owner_timezone": "America/New_York"},
            "2026-11-02T05:00:00+00:00",
        ),
        (
            {"event_at": "2026-03-08", "owner_timezone": "America/New_York"},
            "2026-03-09T04:00:00+00:00",
        ),
        ({"kind": "goal", "event_at": "2026-10-23"}, None),
        ({"kind": "goal", "valid_to": "2026-10-23"}, "2026-10-22T16:00:00+00:00"),
        (
            {
                "kind": "background",
                "slot": "residence_city",
                "valid_to": "2026-10-23",
                "superseded_by": "synthetic-new",
            },
            None,
        ),
        ({"event_at": "明天"}, None),
        ({"event_at": "2026-02-30"}, None),
        ({"event_at": "2026-10-23T20:00:00"}, None),
        ({"event_at": "2026-10-23", "event_end": "未知"}, None),
        ({"event_at": "2026-10-23", "valid_to": "未知"}, None),
        ({"event_at": "2026-10-23", "event_end": "2026-10-21"}, None),
        ({"event_at": "2026-10-23", "owner_timezone": "host-local"}, None),
        ({"event_at": "2026-10-23", "owner_timezone": None}, None),
        ({"event_at": "9999-12-31"}, None),
        ({}, None),
    ],
)
def test_archive_boundaries(fields: dict, expected: str | None) -> None:
    result = archive_deadline({"kind": "event", **fields})
    assert result == (datetime.fromisoformat(expected) if expected else None)
    if result is not None:
        assert result.tzinfo is UTC

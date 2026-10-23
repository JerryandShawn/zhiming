"""Fixed DST and explicit-zone semantics independently checked with UTC expectations."""

from datetime import UTC, datetime

import pytest

from mingjing_core.timeparse.extended_v2 import absolutize_extended, parse_time_range_extended

BASE = datetime(2026, 10, 17, 4, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "zone", "expected"),
    [
        ("November 1, 2026 at 1:30 AM", "America/New_York", {"2026-11-01T05:30:00+00:00", "2026-11-01T06:30:00+00:00"}),
        ("October 25, 2026 at 2:30 AM", "Europe/Berlin", {"2026-10-25T00:30:00+00:00", "2026-10-25T01:30:00+00:00"}),
    ],
)
def test_ambiguous_clock_fold_exposes_both_actual_instants_without_writing_either(text, zone, expected):
    result = parse_time_range_extended(text, BASE, zone)
    actual = {item.start.astimezone(UTC).isoformat() for item in result.candidates if item.start is not None}
    assert result.needs_clarification and expected <= actual
    assert not absolutize_extended(text, BASE, zone).replaced


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("October 28, 2026 at 8 PM UTC", "2026-10-28T20:00:00+00:00"),
        ("October 28, 2026 at 8 PM GMT", "2026-10-28T20:00:00+00:00"),
        ("October 28, 2026 at 8 PM UTC+02:00", "2026-10-28T18:00:00+00:00"),
        ("October 28, 2026 at 8 PM Asia/Shanghai", "2026-10-28T12:00:00+00:00"),
        ("October 28, 2026 at 8 PM America/New_York", "2026-10-29T00:00:00+00:00"),
    ],
)
def test_explicit_zone_takes_precedence_over_owner_zone_without_using_host_zone(text, expected):
    result = parse_time_range_extended(text, BASE, "Asia/Tokyo")
    assert not result.needs_clarification
    assert result.start == result.end == datetime.fromisoformat(expected)


def test_cst_is_not_silently_interpreted_as_one_of_multiple_global_timezones():
    text = "October 28, 2026 at 8 PM CST"
    result = parse_time_range_extended(text, BASE)
    assert result.needs_clarification
    absolute = absolutize_extended(text, BASE)
    assert not absolute.replaced and absolute.text == absolute.original_text == text

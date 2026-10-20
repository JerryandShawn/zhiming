"""The full-regression guard uses Beijing explicitly, regardless of supplied clock zone."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from mingjing_core.timekit.clock import FrozenClock
from tools.mod_week.completed_regression import window_time


@pytest.mark.parametrize("minute", [0, 20, 44])
def test_regression_does_not_start_before_45(minute):
    with pytest.raises(ValueError, match="outside_beijing_window"):
        window_time(FrozenClock(datetime(2026, 10, 20, 16, minute, tzinfo=UTC)))


@pytest.mark.parametrize("minute", [45, 59])
@pytest.mark.parametrize("zone", ["UTC", "Asia/Tokyo", "America/New_York", "Asia/Kolkata"])
def test_legal_start_uses_beijing_not_clock_display_zone(minute, zone):
    at = datetime(2026, 10, 20, 16, minute, tzinfo=UTC).astimezone(ZoneInfo(zone))
    local = window_time(FrozenClock(at))
    assert local.hour == 0 and local.day == 21 and local.minute == minute

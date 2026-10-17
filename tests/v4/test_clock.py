"""Clock freezes the existing Shanghai date without changing its timezone."""

from datetime import UTC, datetime, timedelta

import pytest

from mingjing_core.application.consultation import today
from mingjing_core.timekit import FrozenClock, SystemClock, get_clock, set_clock


@pytest.fixture(autouse=True)
def restore_clock():
    original = get_clock()
    yield
    set_clock(original)


def test_frozen_today_uses_shanghai_date_at_utc_boundary():
    clock = FrozenClock(datetime(2026, 10, 16, 23, 40, tzinfo=UTC))
    set_clock(clock)
    assert today() == "2026-10-17"
    clock.advance(timedelta(days=1))
    assert today() == "2026-10-18"


def test_frozen_clock_normalizes_offset_and_stays_unchanged():
    local = datetime.fromisoformat("2026-10-17T10:30:00+08:00")
    clock = FrozenClock(local)
    assert clock.now() == datetime(2026, 10, 17, 2, 30, tzinfo=UTC)
    assert clock.now().tzinfo is UTC
    assert clock.now() == clock.now()


def test_naive_frozen_time_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        FrozenClock(datetime(2026, 10, 17))


def test_system_clock_returns_aware_utc_instant():
    before = datetime.now(UTC)
    current = SystemClock().now()
    assert current.tzinfo is UTC
    assert before <= current <= datetime.now(UTC)


def test_set_clock_changes_the_module_clock():
    frozen = FrozenClock(datetime(2026, 2, 14, tzinfo=UTC))
    set_clock(frozen)
    assert get_clock() is frozen
    assert today() == "2026-02-14"

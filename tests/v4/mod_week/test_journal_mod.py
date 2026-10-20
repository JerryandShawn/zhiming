"""Hourly dates follow Beijing instants, independent of the host's timezone."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import FrozenClock
from tools.mod_week.journal import append_hour


def test_tokyo_representation_and_utc_representation_share_one_beijing_hour(tmp_path: Path) -> None:
    now = datetime(2026, 10, 20, 15, 10, tzinfo=UTC)
    assert append_hour(FrozenClock(now.astimezone(ZoneInfo("Asia/Tokyo"))), root=tmp_path)
    assert not append_hour(FrozenClock(now), root=tmp_path)
    text = (tmp_path / "docs/v4/daily/2026-10-21_mod.md").read_text(encoding="utf-8")
    assert "2026-10-20 23:10:00 +08:00" in text and "00:10" not in text


def test_records_real_recovery_time_instead_of_inventing_missing_hours(tmp_path: Path) -> None:
    clock = FrozenClock(datetime(2026, 10, 21, 0, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
    assert append_hour(clock, root=tmp_path)
    clock.advance(timedelta(hours=3, minutes=17))
    assert append_hour(clock, root=tmp_path)
    text = (tmp_path / "docs/v4/daily/2026-10-21_mod.md").read_text(encoding="utf-8")
    assert "03:18:00" in text and "2026-10-21 01:" not in text and "2026-10-21 02:" not in text


def test_deadline_is_absolute_beijing_time_and_does_not_create_file(tmp_path: Path) -> None:
    clock = FrozenClock(datetime(2026, 10, 27, 14, tzinfo=UTC))
    assert not append_hour(clock, root=tmp_path)
    assert not (tmp_path / "docs").exists()

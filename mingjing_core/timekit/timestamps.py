"""Interpret legacy naive times as Shanghai while retaining original text."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def history_instant(value) -> datetime | None:
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return stamp.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None

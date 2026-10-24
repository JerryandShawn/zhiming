"""R24: explicit overload is temporary; quota/permission signals always win."""

from __future__ import annotations

import re
from datetime import datetime, timedelta


def is_overloaded(status: int | None, error_type: str = "", message: str = "") -> bool:
    text = (error_type + " " + message).casefold()
    forbidden = r"rate[ _-]?limit|usage[ _-]?limit|quota|concurrency|access[ _-]?terminated|permission|额度|限流|并发"
    return status == 429 and not re.search(forbidden, text) and bool(re.search(r"overload|服务过载", text))


def overload_due(first: datetime, stopped: datetime, index: int) -> datetime | None:
    if type(index) is not int or index < 1 or first.tzinfo is None or stopped.tzinfo is None or first > stopped:
        raise ValueError("R24_OVERLOAD_TIMELINE_REJECTED")
    due = stopped + timedelta(minutes=1 if index <= 5 else 10)
    return due if due <= first + timedelta(minutes=60) else None

"""Only an explicit standard Retry-After becomes an automatic resume boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

from .errors import ModelUnavailable
from .quota_mode import admission_clock


def retry_after(value: Any, now: datetime) -> datetime | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or now.tzinfo is None:
        return None
    try:
        if value.isascii() and value.isdecimal():
            target = now + timedelta(seconds=int(value))
        else:
            target = parsedate_to_datetime(value)
        if target.tzinfo is not None and now < target <= now + timedelta(days=7):
            return target.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        return None
    return None


def attach_reset(failure: Any, headers: Any) -> Any:
    if failure.kind == "quota_5h":
        failure.provider_reset_at = retry_after(headers.get("Retry-After"), admission_clock().now())
    return failure


@contextmanager
def reset_errors(headers: Any) -> Iterator[None]:
    try:
        yield
    except ModelUnavailable as failure:
        attach_reset(failure, headers)
        raise

"""Explicit confirmed clock metadata; a numeric UTC offset never supplies IANA."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_profile_time_basis(fields: dict[str, Any]) -> None:
    if "birth.location.tz" in fields:
        zone = fields["birth.location.tz"]
        if not isinstance(zone, str) or not zone or len(zone) > 100:
            raise ValueError("请明确选择出生地的IANA时区")
        try:
            ZoneInfo(zone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValueError("出生地时区需要有效的IANA名称，不能只填UTC偏移") from None
    if "birth.clock_basis" in fields and fields["birth.clock_basis"] not in ("clock", "standard", "unknown"):
        raise ValueError("请明确核对出生记录采用钟表时间、标准时间或依据不确定")

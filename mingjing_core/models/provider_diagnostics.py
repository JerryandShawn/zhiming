"""Retain only audited public quota sentences, never arbitrary provider text."""

from __future__ import annotations

import json
import re
from typing import Any

PUBLIC_QUOTA = re.compile(r"You['’]ve reached your (?:5-hour|weekly \(7-day\)) usage limit\.?", re.IGNORECASE)
ERROR_TYPES = frozenset({"permission_error", "rate_limit_error", "insufficient_quota", "billing_error"})
QUOTA_SUBTYPES = frozenset({"quota", "quota_5h", "quota_weekly"})


def public_quota_message(value: object) -> str | None:
    """A response may echo a prompt; even its first 240 characters are untrusted."""
    match = PUBLIC_QUOTA.search(value) if isinstance(value, str) else None
    return match[0][:240] if match else None


def error_fields(data: object) -> tuple[str | None, str]:
    if not isinstance(data, dict):
        return None, ""
    error = data.get("error", data)
    if not isinstance(error, dict):
        return None, ""
    kind, message = error.get("type"), error.get("message")
    return kind if isinstance(kind, str) and kind in ERROR_TYPES else None, message if isinstance(message, str) else ""


def parse_error_sample(sample: str) -> Any:
    try:
        return json.loads(sample)
    except (ValueError, TypeError):
        return None


def quota_subtype(message: str) -> str:
    value = message.casefold()
    if "weekly" in value or "7-day" in value:
        return "quota_weekly"
    return "quota_5h" if "5-hour" in value else "quota"


def permission_quota(data: object) -> tuple[str, str] | None:
    if not isinstance(data, dict) or not isinstance(data.get("error"), dict):
        return None
    kind, message = error_fields(data)
    if kind != "permission_error" or "usage limit" not in message.casefold():
        return None
    return quota_subtype(message), public_quota_message(message) or ""

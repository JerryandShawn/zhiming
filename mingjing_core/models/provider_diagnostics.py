"""Retain only audited public quota sentences, never arbitrary provider text."""

from __future__ import annotations

import json
import re
from typing import Any

PUBLIC_QUOTA = re.compile(
    r"You['’]ve reached your (?:(?:5-hour|weekly \(7-day\)) usage limit"
    r"|monthly usage limit for this billing cycle)\.?",
    re.IGNORECASE,
)
ERROR_TYPES = frozenset(
    {
        "permission_error",
        "rate_limit_error",
        "insufficient_quota",
        "billing_error",
        "invalid_request_error",
        "overloaded_error",
        "api_error",
        "access_terminated",
        "concurrency_limited",
    }
)
QUOTA_SUBTYPES = frozenset({"quota", "quota_5h", "quota_weekly", "quota_monthly"})
_QUOTA_PATTERNS = (
    ("quota_monthly", r"monthly\s+(?:usage\s+)?limit|月(?:度)?额度(?:已)?(?:用完|用尽|耗尽)"),
    (
        "quota_weekly",
        r"(?:weekly(?:\s*\(7-day\))?|7[- ]day)\s+(?:usage\s+)?limit|(?:每周|7\s*天).{0,24}(?:额度|用量|上限)",
    ),
    ("quota_5h", r"5[- ]hour\s+(?:usage\s+)?limit|5\s*小时.{0,24}(?:额度|用量|上限)"),
    ("quota", r"you['’]ve reached your usage limit|已达到使用额度上限"),
)


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


def nested_error_fields(data: object) -> tuple[str | None, str]:
    if not isinstance(data, dict) or not isinstance(data.get("error"), dict):
        return None, ""
    return error_fields(data)


def parse_error_sample(sample: str) -> Any:
    try:
        return json.loads(sample)
    except (ValueError, TypeError):
        return None


def quota_subtype(message: str) -> str:
    return next((kind for kind, pattern in _QUOTA_PATTERNS if re.search(pattern, message, re.IGNORECASE)), "quota")


def permission_quota(data: object) -> tuple[str, str] | None:
    if not isinstance(data, dict) or not isinstance(data.get("error"), dict):
        return None
    kind, message = nested_error_fields(data)
    if kind != "permission_error" or not any(
        re.search(pattern, message, re.IGNORECASE) for _, pattern in _QUOTA_PATTERNS
    ):
        return None
    return quota_subtype(message), public_quota_message(message) or ""

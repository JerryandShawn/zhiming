"""A private source is usable in its thread, never a long-term memory authority."""

from __future__ import annotations

from typing import Any

from mingjing_core.domain.contracts import EvidenceError


def is_private(value: dict[str, Any]) -> bool:
    return value.get("incognito") is True or str(value.get("thread_id", "")).startswith("incognito:")


def require_persistent_source(value: dict[str, Any]) -> None:
    if is_private(value) or value.get("policy", {}).get("persist_allowed") is False:
        raise EvidenceError("无痕原话不能授权长期记忆或资料")

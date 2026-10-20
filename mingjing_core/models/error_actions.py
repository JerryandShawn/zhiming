"""Immutable error actions; execution and persistent stops belong to callers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal


@dataclass(frozen=True)
class ErrorActions:
    retry: Literal["never", "transient", "membership_once", "protocol_once"] = "never"
    max_attempts: int = 1
    delays_seconds: tuple[float, ...] = ()
    fallback: Literal["none", "configured_nonmembership"] = "none"
    global_stop: bool = False
    persistent_stop: bool = False
    stop_reason: str | None = None
    manual_clear: bool = False
    resume_after_seconds: int | None = None
    notice: str | None = None


NEVER = ErrorActions()
PROVIDER_QUOTA = ErrorActions(fallback="configured_nonmembership")
TRANSIENT = ErrorActions("transient", 4, (1.0, 3.0, 9.0), "configured_nonmembership")
MEMBERSHIP_ONCE = ErrorActions("membership_once", 2, (60.0,), "configured_nonmembership")
PROTOCOL_ONCE = ErrorActions("protocol_once", 2, (1.0,), "configured_nonmembership")

_STOPS = {
    "quota": (True, None, "会员额度暂不可用，请确认恢复时间后再继续"),
    "quota_5h": (False, 18000, "会员5小时额度暂不可用，恢复后仍需明确开始下一批"),
    "quota_weekly": (True, None, "线上可能受影响：Kimi 会员周额度已用完"),
    "quota_monthly": (True, None, "你的 Kimi 会员月额度已用完，Kimi 网页版、Kimi Code 等都会受影响。"),
    "concurrency_limited": (True, None, "Kimi 会员端点触发并发风控，已停止全部调用。"),
    "access_terminated": (True, None, "Kimi 会员端点访问已终止，已停止全部调用。"),
}


def actions_for_kind(kind: str) -> ErrorActions:
    if kind in _STOPS:
        manual, seconds, notice = _STOPS[kind]
        return replace(
            NEVER,
            global_stop=True,
            persistent_stop=True,
            stop_reason=kind,
            manual_clear=manual,
            resume_after_seconds=seconds,
            notice=notice,
        )
    if kind == "membership_unverified":
        return MEMBERSHIP_ONCE
    if kind in {"rate_limited", "engine_overloaded", "unavailable"}:
        return TRANSIENT
    return PROTOCOL_ONCE if kind == "protocol_error" else NEVER

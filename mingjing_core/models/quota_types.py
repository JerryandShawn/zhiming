"""Body-free policy and errors for the central membership ledger."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from .error_actions import NEVER, actions_for_kind
from .errors import ModelBadRequest

ROLES = frozenset({"primary", "critic", "fast", "vision", "evaluation", "background"})
LANES = frozenset({"interactive", "background", "eval", "probe"})
STOP_KINDS = frozenset(
    {
        "member_window_limit",
        "quota",
        "quota_5h",
        "quota_weekly",
        "quota_monthly",
        "concurrency_limited",
        "access_terminated",
    }
)
RESULT_KINDS = STOP_KINDS | frozenset(
    {
        "ok",
        "unavailable",
        "cancelled",
        "protocol_error",
        "rate_limited",
        "engine_overloaded",
        "bad_request",
        "content_filtered",
        "payload_too_large",
        "token_limit",
        "permission_error",
        "reasoning_missing",
        "membership_unverified",
        "capability_error",
        "unknown",
    }
)


class GuardConfigurationError(ValueError):
    code = "MEMBER_GUARD_CONFIGURATION"


class GuardRejected(ModelBadRequest):
    code = "MEMBER_GUARD_REJECTED"
    allowed_kinds = STOP_KINDS | frozenset(
        {
            "member_window_limit",
            "share_limit",
            "in_flight_limit",
            "batch_cooldown",
            "manual_start_required",
            "authorization_expired",
            "batch_conflict",
            "attempt_replayed",
            "clock_rollback",
            "ledger_unavailable",
        }
    )

    def __init__(self, kind: str, resume_at: datetime | None = None) -> None:
        if kind not in self.allowed_kinds:
            kind = "ledger_unavailable"
        actions = actions_for_kind(kind) if kind in STOP_KINDS else NEVER
        if kind in STOP_KINDS:
            actions = replace(
                actions,
                global_stop=True,
                persistent_stop=True,
                manual_clear=True,
                stop_reason=kind,
            )
        super().__init__(kind=kind, retry_actions=actions)
        self.resume_at = resume_at
        self.args = ("会员调用暂已停止，请核对中央守卫和本批授权",)

    def safe_diagnostic(self) -> dict[str, Any]:
        result = super().safe_diagnostic()
        if self.resume_at is not None:
            result["resume_at"] = self.resume_at.isoformat()
        return result


def identifier(value: str, *, maximum: int = 160) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value) is None
    ):
        raise GuardConfigurationError("中央守卫标识无效")
    return value


def instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise GuardConfigurationError("中央守卫时间必须包含时区")
    return value.astimezone(UTC)


def bucket(role: str, lane: str) -> str:
    if role not in ROLES or lane not in LANES:
        raise GuardConfigurationError("中央守卫角色或通道无效")
    if role == "background" and lane == "interactive":
        raise GuardConfigurationError("后台角色不能占用交互预留")
    return "critic" if role == "critic" else "interactive" if lane == "interactive" else "background"


@dataclass(frozen=True)
class QuotaPolicy:
    max_calls: int = 80
    eval_max_calls: int = 80
    interactive_share: float = 0.60
    critic_share: float = 0.20
    background_share: float = 0.20
    window: timedelta = timedelta(hours=5)
    batch_gap: timedelta = timedelta(minutes=20)

    def __post_init__(self) -> None:
        if type(self.max_calls) is not int or not 1 <= self.max_calls <= 80:
            raise GuardConfigurationError("中央守卫窗口上限无效")
        if type(self.eval_max_calls) is not int or not 1 <= self.eval_max_calls <= 80:
            raise GuardConfigurationError("中央守卫评测上限无效")
        shares = (self.interactive_share, self.critic_share, self.background_share)
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in shares):
            raise GuardConfigurationError("中央守卫预算份额无效")
        if (
            not math.isclose(sum(shares), 1)
            or not isinstance(self.window, timedelta)
            or not isinstance(self.batch_gap, timedelta)
            or self.window < timedelta(hours=5)
            or self.batch_gap < timedelta(minutes=20)
        ):
            raise GuardConfigurationError("中央守卫不能放宽既定预算边界")

    def limit(self, name: str) -> int:
        return max(1, math.floor(self.max_calls * getattr(self, name + "_share")))

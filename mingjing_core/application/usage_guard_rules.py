"""Continuous-usage signals; current P7 D4 defaults on, users may disable. Nothing is sent."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from mingjing_core.timekit.clock import Clock


@dataclass(frozen=True)
class UsageEvent:
    id: str
    owner_id: str
    at: datetime
    interactive: bool = True

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.id, self.owner_id)
        ):
            raise ValueError("时长事件缺少归属或标识")
        if type(self.interactive) is not bool:
            raise ValueError("交互标志必须为明确布尔值")
        object.__setattr__(self, "at", _utc(self.at))


@dataclass(frozen=True)
class UsagePolicy:
    enabled: bool = True
    minutes: int = 120
    cooldown_minutes: int = 120
    gap_minutes: int = 10

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or any(
            type(value) is not int or value <= 0
            for value in (self.minutes, self.cooldown_minutes, self.gap_minutes)
        ):
            raise ValueError("时长提醒设置无效")


DEFAULT_USAGE_POLICY = UsagePolicy()


@dataclass(frozen=True)
class UsageState:
    owner_id: str
    last_reminded_at: datetime | None = None
    deferred_on: date | None = None
    deferred_session_start: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.owner_id, str) or not self.owner_id.strip():
            raise ValueError("时长提醒缺少归属")
        if self.deferred_on is not None and type(self.deferred_on) is not date:
            raise ValueError("延后日期无效")
        for name in ("last_reminded_at", "deferred_session_start"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _utc(value))


@dataclass(frozen=True)
class UsageDecision:
    should_remind: bool
    continuous_minutes: float
    reason: str
    next_state: UsageState


def _utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("时长事件必须有时区")
    return value.astimezone(UTC)


def _session_start(
    events: Sequence[UsageEvent],
    owner_id: str,
    now: datetime,
    timezone: str,
    gap_minutes: int,
) -> datetime:
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    unique: dict[str, datetime] = {}
    for event in events:
        if event.owner_id != owner_id or not event.interactive:
            continue
        instant = _utc(event.at)
        if instant > now:
            raise ValueError("时长事件时间超前")
        if event.id in unique and unique[event.id] != instant:
            raise ValueError("时长事件标识冲突")
        unique[event.id] = instant
    stamps = sorted(
        instant
        for instant in unique.values()
        if instant.astimezone(zone).date() == today
    )
    start = stamps[0] if stamps else now
    last = start
    for instant in stamps[1:] + [now]:
        if instant - last >= timedelta(minutes=gap_minutes):
            start = instant
        last = instant
    return start


def usage_decision(
    events: Sequence[UsageEvent],
    state: UsageState,
    *,
    clock: Clock,
    timezone: str = "Asia/Shanghai",
    policy: UsagePolicy = DEFAULT_USAGE_POLICY,
    crisis: bool = False,
    confirming_data: bool = False,
) -> UsageDecision:
    if not state.owner_id:
        raise ValueError("时长提醒缺少owner")
    if not policy.enabled:
        return UsageDecision(False, 0.0, "disabled", state)
    now = _utc(clock.now())
    today = now.astimezone(ZoneInfo(timezone)).date()
    start = _session_start(events, state.owner_id, now, timezone, policy.gap_minutes)
    duration = (now - start).total_seconds() / 60
    pending = state.deferred_on == today and state.deferred_session_start == start
    if not pending and (
        state.deferred_on is not None or state.deferred_session_start is not None
    ):
        state = replace(state, deferred_on=None, deferred_session_start=None)
    if crisis:
        return UsageDecision(False, duration, "crisis", state)
    if duration <= policy.minutes and not pending:
        return UsageDecision(False, duration, "below_threshold", state)
    if state.last_reminded_at is not None:
        elapsed = now - _utc(state.last_reminded_at)
        if elapsed < timedelta(0):
            raise ValueError("时长提醒状态时间超前")
        if elapsed < timedelta(minutes=policy.cooldown_minutes):
            return UsageDecision(False, duration, "cooldown", state)
    if confirming_data:
        return UsageDecision(
            False,
            duration,
            "confirmation_deferred",
            UsageState(state.owner_id, state.last_reminded_at, today, start),
        )
    return UsageDecision(
        True, duration, "long_session", UsageState(state.owner_id, now, None)
    )

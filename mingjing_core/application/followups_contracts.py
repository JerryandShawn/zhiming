"""Immutable projections for offline proactive rules; callers own durable scoped state."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

NoticeKind = Literal["followup", "brief", "reminder"]
ResponseStatus = Literal["pending", "replied", "ignored", "muted"]


def aware(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("主动消息时间必须包含时区")
    return value.astimezone(UTC)


def _identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 250:
        raise ValueError("主动消息标识或归属无效")


def _flags(values: Iterable[bool]) -> None:
    if any(type(value) is not bool for value in values):
        raise ValueError("主动消息开关必须是布尔值")


@dataclass(frozen=True)
class FollowupScope:
    owner_id: str
    subject_id: str

    def __post_init__(self) -> None:
        _identity(self.owner_id)
        _identity(self.subject_id)

    def require(self, owner_id: str, subject_id: str) -> None:
        if (owner_id, subject_id) != (self.owner_id, self.subject_id):
            raise ValueError("主动消息不能跨用户或人物归属")


@dataclass(frozen=True)
class FollowupSettings:
    timezone: str = "Asia/Shanghai"
    daily_cap: int = 2
    proactive_enabled: bool = True
    followups_enabled: bool = True
    quiet_start: time = time(22)
    quiet_end: time = time(8)
    resume_at: time = time(8, 30)
    muted_categories: frozenset[str] = field(default=frozenset(), repr=False)

    def __post_init__(self) -> None:
        ZoneInfo(self.timezone)
        if type(self.daily_cap) is not int or not 0 <= self.daily_cap <= 2:
            raise ValueError("每天主动消息上限必须在0至2之间")
        _flags((self.proactive_enabled, self.followups_enabled))
        for value in (self.quiet_start, self.quiet_end, self.resume_at):
            if not isinstance(value, time) or value.tzinfo is not None:
                raise ValueError("免打扰时刻必须是当地无时区时刻")
        if self.quiet_start == self.quiet_end:
            raise ValueError("免打扰起止时刻不能相同")
        during_quiet = (
            self.quiet_start <= self.resume_at < self.quiet_end
            if self.quiet_start < self.quiet_end
            else self.resume_at >= self.quiet_start or self.resume_at < self.quiet_end
        )
        if during_quiet:
            raise ValueError("顺延恢复时刻必须在免打扰时段之外")
        if not isinstance(self.muted_categories, frozenset) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.muted_categories
        ):
            raise ValueError("静音类别必须是不可变非空标签集合")


@dataclass(frozen=True)
class FollowupCandidate:
    id: str
    owner_id: str
    subject_id: str
    kind: NoticeKind
    due_at: datetime
    category: str = field(default="", repr=False)
    active: bool = True
    source_active: bool = True
    source_revoked: bool = False
    explicit_requested: bool = False
    explicit_quiet_time: bool = False
    essential: bool = False
    sensitive: bool = False
    text: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        for value in (self.id, self.owner_id, self.subject_id):
            _identity(value)
        object.__setattr__(self, "due_at", aware(self.due_at))
        if self.kind not in {"followup", "brief", "reminder"} or not isinstance(
            self.category, str
        ):
            raise ValueError("主动消息类型或类别无效")
        _flags(
            (
                self.active,
                self.source_active,
                self.source_revoked,
                self.explicit_requested,
                self.explicit_quiet_time,
                self.essential,
                self.sensitive,
            )
        )
        if not isinstance(self.text, str):
            raise ValueError("主动消息预览必须是文本")
        if self.explicit_quiet_time and not (
            self.kind == "reminder" and self.explicit_requested
        ):
            raise ValueError("免打扰例外必须来自用户明确设定的提醒时刻")


@dataclass(frozen=True)
class ProactiveNotice:
    id: str
    owner_id: str
    subject_id: str
    kind: NoticeKind
    sent_at: datetime
    category: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        for value in (self.id, self.owner_id, self.subject_id):
            _identity(value)
        object.__setattr__(self, "sent_at", aware(self.sent_at))
        if self.kind not in {"followup", "brief", "reminder"} or not isinstance(
            self.category, str
        ):
            raise ValueError("主动消息记录类型无效")


@dataclass(frozen=True)
class UserActivity:
    id: str
    owner_id: str
    subject_id: str
    at: datetime

    def __post_init__(self) -> None:
        for value in (self.id, self.owner_id, self.subject_id):
            _identity(value)
        object.__setattr__(self, "at", aware(self.at))


@dataclass(frozen=True)
class ResponseObservation:
    notice: ProactiveNotice
    status: ResponseStatus
    observed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", aware(self.observed_at))
        if self.status not in {"pending", "replied", "ignored", "muted"}:
            raise ValueError("主动消息响应状态无效")
        if self.observed_at < self.notice.sent_at:
            raise ValueError("响应判定不能早于消息发送时间")
        if (
            self.status == "ignored"
            and self.observed_at < self.notice.sent_at + timedelta(hours=24)
        ):
            raise ValueError("未满24小时不能投影为已忽略")


@dataclass(frozen=True)
class ReceptivityState:
    owner_id: str
    subject_id: str
    ignored_streak: int = 0
    pause_until: datetime | None = None
    brief_ignore_days: tuple[date, ...] = ()
    brief_prompt_pending: bool = False
    brief_prompted_at: datetime | None = None
    muted_categories: frozenset[str] = field(default=frozenset(), repr=False)
    observations: tuple[ResponseObservation, ...] = field(default=(), repr=False)

    def __post_init__(self) -> None:
        _identity(self.owner_id)
        _identity(self.subject_id)
        if type(self.ignored_streak) is not int or not 0 <= self.ignored_streak <= 2:
            raise ValueError("未回应计数无效")
        _flags((self.brief_prompt_pending,))
        for name in ("pause_until", "brief_prompted_at"):
            instant = getattr(self, name)
            if instant is not None:
                object.__setattr__(self, name, aware(instant))
        if not isinstance(self.muted_categories, frozenset) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.muted_categories
        ):
            raise ValueError("静音类别必须是不可变非空标签集合")
        if not isinstance(self.observations, tuple) or len(
            {item.notice.id for item in self.observations}
        ) != len(self.observations):
            raise ValueError("响应观察必须是唯一消息的不可变序列")
        scope = FollowupScope(self.owner_id, self.subject_id)
        for item in self.observations:
            scope.require(item.notice.owner_id, item.notice.subject_id)
        if not isinstance(self.brief_ignore_days, tuple) or any(
            type(day) is not date for day in self.brief_ignore_days
        ):
            raise ValueError("晨报日期必须是不可变本地日序列")


@dataclass(frozen=True)
class DeliveryDecision:
    allowed: bool
    next_due: datetime | None
    reason: str
    daily_cap: int
    preview: str = field(repr=False)

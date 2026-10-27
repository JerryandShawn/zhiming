"""Opaque capability metadata; no private action payload or raw token is stored here."""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime


class ActionTokenError(ValueError):
    code = "ACTION_TOKEN_INVALID"

    def __init__(self) -> None:
        super().__init__("这个操作已失效，请从最新卡片重新选择。")


def utc(value: datetime) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ActionTokenError()
    return value.astimezone(UTC)


def validate_identity(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 250
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ActionTokenError()
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise ActionTokenError() from None


def validate_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ActionTokenError()


@dataclass(frozen=True, repr=False)
class ActionTokenClaim:
    owner_id: str
    subject_id: str
    open_id: str
    kind: str
    entity_id: str
    payload_fingerprint: str

    def __post_init__(self) -> None:
        for value in (self.owner_id, self.subject_id, self.entity_id):
            validate_identity(value)
        # 回调 open_id 字段及其 SDK 映射待对照飞书官方文档核实；本模块沿用 Core 既有绑定格式。
        if (
            not isinstance(self.open_id, str)
            or re.fullmatch(r"ou_[A-Za-z0-9]{1,200}", self.open_id) is None
        ):
            raise ActionTokenError()
        if (
            not isinstance(self.kind, str)
            or re.fullmatch(r"[a-z][a-z0-9_.:-]{0,63}", self.kind) is None
        ):
            raise ActionTokenError()
        validate_digest(self.payload_fingerprint)


@dataclass(frozen=True, repr=False)
class ActionTokenRecord:
    digest: str
    claim: ActionTokenClaim
    created_at: datetime
    expires_at: datetime
    operation_id: str
    used_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_digest(self.digest)
        if not isinstance(self.claim, ActionTokenClaim):
            raise ActionTokenError()
        object.__setattr__(self, "created_at", utc(self.created_at))
        object.__setattr__(self, "expires_at", utc(self.expires_at))
        if self.expires_at <= self.created_at:
            raise ActionTokenError()
        if (
            not isinstance(self.operation_id, str)
            or re.fullmatch(r"feishu-card:[a-f0-9]{64}", self.operation_id) is None
        ):
            raise ActionTokenError()
        if self.used_at is not None:
            object.__setattr__(self, "used_at", utc(self.used_at))
            if not self.created_at <= self.used_at < self.expires_at:
                raise ActionTokenError()


@dataclass(frozen=True)
class IssuedActionToken:
    token: str = field(repr=False)
    expires_at: datetime
    operation_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.token, str)
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", self.token) is None
        ):
            raise ActionTokenError()
        object.__setattr__(self, "expires_at", utc(self.expires_at))


@dataclass(frozen=True)
class TokenConsumption:
    owner_id: str = field(repr=False)
    subject_id: str = field(repr=False)
    kind: str
    entity_id: str = field(repr=False)
    payload_fingerprint: str = field(repr=False)
    operation_id: str
    used_at: datetime
    replayed: bool

    def __post_init__(self) -> None:
        for value in (self.owner_id, self.subject_id, self.entity_id):
            validate_identity(value)
        validate_digest(self.payload_fingerprint)
        if type(self.replayed) is not bool:
            raise ActionTokenError()
        object.__setattr__(self, "used_at", utc(self.used_at))

    @property
    def should_execute(self) -> bool:
        return not self.replayed

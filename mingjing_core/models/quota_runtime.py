"""Explicit central ledger location and trusted per-operation membership scope."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from mingjing_core.timekit.clock import SystemClock

from .quota_guard import QuotaGuard
from .quota_types import LANES, GuardConfigurationError, GuardRejected, identifier

ENVIRONMENT = {
    "central_dsn": "MEMBER_CENTRAL_DSN",
    "central_schema": "MEMBER_CENTRAL_SCHEMA",
    "account_id": "MEMBER_ACCOUNT_ID",
    "ledger_identity": "MEMBER_LEDGER_IDENTITY",
}


@dataclass(frozen=True)
class CallScope:
    lane: str | None = None
    run_id: str | None = None
    batch_id: str | None = None
    authorization_id: str | None = None
    scenario_id: str | None = None

    def __post_init__(self) -> None:
        if self.lane is not None and self.lane not in LANES:
            raise GuardConfigurationError("调用通道无效")
        for value in (
            self.run_id,
            self.batch_id,
            self.authorization_id,
            self.scenario_id,
        ):
            if value is not None:
                identifier(value)


_SCOPE: ContextVar[CallScope | None] = ContextVar("member_call_scope", default=None)


def current_scope() -> CallScope:
    return _SCOPE.get() or CallScope()


@contextmanager
def call_scope(scope: CallScope) -> Iterator[None]:
    token = _SCOPE.set(scope)
    try:
        yield
    finally:
        _SCOPE.reset(token)


@dataclass(frozen=True)
class CentralLocation:
    central_dsn: str = field(repr=False)
    central_schema: str
    account_id: str
    ledger_identity: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> CentralLocation:
        source = os.environ if environment is None else environment
        values = {key: source.get(name, "") for key, name in ENVIRONMENT.items()}
        if not all(values.values()):
            raise GuardRejected("ledger_unavailable")
        return cls(**values)

    def guard(self) -> QuotaGuard:
        try:
            return QuotaGuard(
                central_dsn=self.central_dsn,
                central_schema=self.central_schema,
                account_id=self.account_id,
                ledger_identity=self.ledger_identity,
                clock=SystemClock(),
            )
        except GuardConfigurationError:
            raise GuardRejected("ledger_unavailable") from None

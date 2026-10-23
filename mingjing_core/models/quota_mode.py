"""Verified PG admission sets this context; request data cannot select a policy."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from mingjing_core.timekit.clock import Clock, SystemClock

_DELEGATED: ContextVar[bool] = ContextVar("verified_member_delegation", default=False)
_SESSION: ContextVar[Any] = ContextVar("trusted_member_delegation_session", default=None)
_ADMISSION_CLOCK: ContextVar[Clock | None] = ContextVar("member_admission_clock", default=None)


def admission_clock() -> Clock:
    return _ADMISSION_CLOCK.get() or SystemClock()


def current_delegated_session() -> Any:
    return _SESSION.get()


@contextmanager
def delegated_session(session: Any) -> Iterator[None]:
    if _SESSION.get() is not None:
        from .quota_types import GuardRejected

        raise GuardRejected("batch_conflict")
    token = _SESSION.set(session)
    try:
        yield
    finally:
        _SESSION.reset(token)


def delegated_active() -> bool:
    return _DELEGATED.get()


@contextmanager
def verified_delegated_attempt(enabled: bool, clock: Clock) -> Iterator[None]:
    token = _DELEGATED.set(enabled)
    clock_token = _ADMISSION_CLOCK.set(clock)
    try:
        yield
    finally:
        _ADMISSION_CLOCK.reset(clock_token)
        _DELEGATED.reset(token)

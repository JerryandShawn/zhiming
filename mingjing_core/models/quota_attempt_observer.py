"""Optional trusted step observation; a provider request never enables it itself."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol

from .error_actions import NEVER
from .errors import ModelUnavailable


class ModelAttemptUnconfirmed(ModelUnavailable):
    code = "MODEL_ATTEMPT_UNCONFIRMED"
    default_kind = "ledger_unavailable"
    allowed_kinds = frozenset({"ledger_unavailable"})

    def __init__(self) -> None:
        super().__init__(retry_actions=NEVER)


class AttemptObserver(Protocol):
    def prepare(self, guard: Any, scope: Any, attempt_id: str, role: str, provider: str, model: str) -> None: ...

    def admitted(self, guard: Any, scope: Any, attempt_id: str) -> None: ...

    def finished(self, guard: Any, scope: Any, attempt_id: str) -> None: ...

    def before_send(self) -> None: ...


_OBSERVER: ContextVar[AttemptObserver | None] = ContextVar("model_step_attempt_observer", default=None)
_COUNTERS: ContextVar[list[Callable[[], None]] | None] = ContextVar("model_attempt_send_counters", default=None)


def current_observer() -> AttemptObserver | None:
    return _OBSERVER.get()


def before_observed_send() -> None:
    if observer := current_observer():
        observer.before_send()
        counters = _COUNTERS.get()
        if counters is None:
            raise ModelAttemptUnconfirmed()
        pending, counters[:] = list(counters), []
        for callback in pending:
            callback()


def defer_send_counter(callback: Callable[[], None]) -> bool:
    if current_observer() is None:
        return False
    counters = _COUNTERS.get()
    if counters is None or counters:
        raise ModelAttemptUnconfirmed()
    counters.append(callback)
    return True


@contextmanager
def per_physical_send() -> Iterator[None]:
    if current_observer() is None:
        yield
        return
    token = _COUNTERS.set([])
    try:
        yield
    finally:
        _COUNTERS.reset(token)


@contextmanager
def observe_attempts(observer: AttemptObserver) -> Iterator[None]:
    token = _OBSERVER.set(observer)
    try:
        yield
    finally:
        _OBSERVER.reset(token)

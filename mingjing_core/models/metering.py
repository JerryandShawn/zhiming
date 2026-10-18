"""Optional request-local metering; production has no evaluation dependency."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_BEFORE_REQUEST: ContextVar[Callable[[], None] | None] = ContextVar("model_request_meter", default=None)


def before_provider_request() -> None:
    callback = _BEFORE_REQUEST.get()
    if callback is not None:
        callback()


@contextmanager
def request_meter(callback: Callable[[], None] | None) -> Iterator[None]:
    if callback is None:
        yield
        return
    token = _BEFORE_REQUEST.set(callback)
    try:
        yield
    finally:
        _BEFORE_REQUEST.reset(token)

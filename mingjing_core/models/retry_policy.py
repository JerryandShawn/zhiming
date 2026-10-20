"""One bounded retry policy shared by registry calls and direct HTTP adapters."""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from .errors import ModelUnavailable


def retry_delay(failure: ModelUnavailable, attempt: int, maximum_retries: int, *, visible: bool) -> float | None:
    actions = failure.retry_actions
    if visible or actions.global_stop or actions.retry == "never":
        return None
    if attempt >= maximum_retries or attempt + 1 >= actions.max_attempts or not actions.delays_seconds:
        return None
    delay = actions.delays_seconds[min(attempt, len(actions.delays_seconds) - 1)]
    return delay if actions.retry == "membership_once" else delay + random.uniform(0, 0.2)


def wait_for_retry(
    delay: float,
    deadline: float,
    cancel: threading.Event | None,
    sleep: Callable[[float], None],
) -> bool:
    remaining = deadline - time.monotonic()
    if remaining <= 0 or cancel is not None and cancel.is_set():
        return False
    duration = min(delay, remaining)
    if cancel is not None and sleep is time.sleep:
        cancel.wait(duration)
    else:
        sleep(duration)
    return time.monotonic() < deadline and not (cancel is not None and cancel.is_set())

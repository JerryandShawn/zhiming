"""A central permit surrounds each physical POST, including retries and stream closure."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import ModelUnavailable
from .quota_attempt_observer import current_observer, per_physical_send
from .quota_guard import Attempt, QuotaGuard, _propagated_error
from .quota_mode import current_delegated_session
from .quota_runtime import CentralLocation, current_scope
from .quota_types import ROLES, GuardRejected, bucket


def membership_endpoint(base_url: str, provider: str = "") -> bool:
    url = urlsplit(base_url)
    return provider == "kimi_code" or url.hostname == "api.kimi.com" and url.path.startswith("/coding")


def lane_for(role: str) -> str:
    if role not in ROLES:
        raise GuardRejected("ledger_unavailable")
    return "eval" if role == "evaluation" else "background" if role in {"fast", "background"} else "interactive"


@contextmanager
def provider_attempt(
    *,
    membership: bool,
    role: str,
    provider: str,
    model: str,
    transport: httpx.BaseTransport | None = None,
    guard: QuotaGuard | None = None,
    cancel_event: threading.Event | None = None,
    timeout: float | None = None,
) -> Iterator[Attempt | None]:
    if not membership:
        yield None
        return
    session = current_delegated_session()
    if guard is None and session is None and isinstance(transport, httpx.MockTransport):
        # A MockTransport cannot issue a physical provider request. PG integration
        # tests pass a real guard explicitly; this is not a runtime HTTP exemption.
        yield None
        return
    active = session.guard if session is not None else guard or CentralLocation.from_environment().guard()
    if session is not None and guard is not None and guard is not session.guard:
        raise GuardRejected("ledger_unavailable")
    scope = current_scope()
    with (
        session.permit_scope(scope) if session is not None else nullcontext(scope) as admitted,
        _admitted_attempt(active, admitted, role, provider, model, cancel_event, timeout) as attempt,
    ):
        yield attempt


@contextmanager
def _admitted_attempt(
    active: QuotaGuard,
    scope: Any,
    role: str,
    provider: str,
    model: str,
    cancel_event: threading.Event | None,
    timeout: float | None,
) -> Iterator[Attempt]:
    lane = scope.lane or lane_for(role)
    bucket(role, lane)
    attempt_id, observer = "http-" + uuid.uuid4().hex, current_observer()
    if observer is not None:
        observer.prepare(active, scope, attempt_id, role, provider, model)
    error = finish_error = None
    try:
        with _guarded_attempt(active, scope, role, provider, model, cancel_event, timeout, attempt_id) as attempt:
            yield attempt
    except BaseException as caught:
        error = caught
    if observer is not None:
        try:
            observer.finished(active, scope, attempt_id)
        except BaseException as caught:
            finish_error = caught
    failure = _propagated_error(error, finish_error)
    if failure is not None:
        raise failure from None


@contextmanager
def _guarded_attempt(
    active: QuotaGuard,
    scope: Any,
    role: str,
    provider: str,
    model: str,
    cancel_event: threading.Event | None,
    timeout: float | None,
    attempt_id: str,
) -> Iterator[Attempt]:
    with active.acquire(
        role,
        scope.lane or lane_for(role),
        attempt_id=attempt_id,
        provider=provider,
        model=model,
        run_id=scope.run_id,
        batch_id=scope.batch_id,
        authorization_id=scope.authorization_id,
        scenario_id=scope.scenario_id,
        cancel_event=cancel_event,
        timeout=timeout,
    ) as attempt:
        if observer := current_observer():
            observer.admitted(active, scope, attempt.attempt_id)
        try:
            with per_physical_send():
                yield attempt
        except httpx.HTTPError:
            raise ModelUnavailable() from None


def observe_usage(attempt: Attempt | None, usage: Mapping[str, Any]) -> None:
    if attempt is None:
        return
    names = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "cache_read_tokens": ("cache_read_tokens", "cache_read_input_tokens"),
        "cache_write_tokens": ("cache_write_tokens", "cache_creation_input_tokens"),
    }
    values = dict(attempt.usage)
    for target, candidates in names.items():
        for key in candidates:
            value = usage.get(key)
            if type(value) is int and value >= 0:
                values[target] = value
                break
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict) and type(value := details.get("cached_tokens")) is int and value >= 0:
        values["cache_read_tokens"] = value
    attempt.result(usage=values)

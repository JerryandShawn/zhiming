"""HTTP/SSE transport with safe retries, cancellation and a wall-clock deadline."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager, suppress
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from mingjing_core.domain.json_values import ensure_finite_json

from .config_policy import ConfigError, validate_model_settings
from .error_classification import classify_error
from .errors import (
    ModelBadRequest,
    ModelCancelled,
    ModelProtocolError,
    ModelQuotaExhausted,
    ModelUnavailable,
)
from .metering import before_provider_request
from .port import ModelPort, StreamEvent
from .provider_diagnostics import delegated_stop_hint, parse_error_sample
from .provider_reset import attach_reset, reset_errors
from .quota_attempt_observer import before_observed_send
from .quota_guard import QuotaGuard
from .quota_http import membership_endpoint, observe_usage, provider_attempt
from .quota_mode import delegated_active
from .request_policy import check_request_size, sampling_body
from .retry_policy import retry_delay, wait_for_retry
from .turn_coercion import turn_policy


def safe_usage(data: Any) -> dict[str, int]:
    if not isinstance(data, dict):
        return {}
    names = {
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
    }
    result = {
        key: value
        for key, value in (data or {}).items()
        if key in names and type(value) is int and 0 <= value <= 2**63 - 1
    }
    details = data.get("prompt_tokens_details")
    if isinstance(details, dict) and type(value := details.get("cached_tokens")) is int and 0 <= value <= 2**63 - 1:
        result["cache_read_tokens"] = value
    return result


def check_cancel(event: threading.Event | None) -> None:
    if event is not None and event.is_set():
        raise ModelCancelled()


def http_error(response: httpx.Response, *, membership: bool) -> ModelUnavailable:
    # Classification inspects one bounded error sample; no raw text crosses this boundary.
    try:
        sample = next(response.iter_bytes(chunk_size=4096), b"").decode("utf-8", errors="ignore")
    except httpx.HTTPError:
        sample = ""
    observed = delegated_stop_hint(sample) if membership and delegated_active() else None
    return attach_reset(
        classify_error(
            response.status_code,
            parse_error_sample(sample),
            membership=membership,
            observed_stop=observed,
        ),
        response.headers,
    )


def sse(response: httpx.Response, cancel: threading.Event | None) -> Iterator[dict[str, Any]]:
    data: list[str] = []
    for line in response.iter_lines():
        check_cancel(cancel)
        if line.startswith("data:"):
            data.append(line[5:].lstrip())
        elif line == "" and data:
            payload = "\n".join(data)
            data.clear()
            if payload == "[DONE]":
                return
            yield _parse(payload)
    if data and "\n".join(data) != "[DONE]":
        yield _parse("\n".join(data))


def _parse(value: str) -> dict[str, Any]:
    failed = False
    try:
        parsed = strict_json(value)
        failed = not isinstance(parsed, dict)
    except (ValueError, TypeError):
        failed = True
    if failed:
        raise ModelProtocolError()
    return parsed


class Closable(Protocol):
    def close(self) -> None: ...


def _reject_constant(_: str) -> Any:
    raise ValueError("Nonfinite JSON number")


def strict_json(value: str) -> Any:
    return ensure_finite_json(json.loads(value, parse_constant=_reject_constant))


def stream_error(data: Any, *, membership: bool) -> ModelUnavailable:
    return classify_error(None, {"error": data}, membership=membership, surface="sse")


def shutdown_response(response: Closable | None) -> None:
    """Closing an fd alone need not wake another thread blocked in Linux recv."""
    if not isinstance(response, httpx.Response):
        return
    stream = response.extensions.get("network_stream")
    extra = getattr(stream, "get_extra_info", None)
    if callable(extra):
        with suppress(OSError, RuntimeError, AttributeError, TypeError, httpx.HTTPError):
            connection = extra("socket")
            if connection is not None:
                connection.shutdown(socket.SHUT_RDWR)


@contextmanager
def cancellation_errors(cancel: threading.Event | None) -> Iterator[None]:
    try:
        yield
    except (httpx.HTTPError, RuntimeError):
        # Socket shutdown wakes a blocked read as an I/O error. Classify the
        # cancellation before the enclosing central permit records its result.
        check_cancel(cancel)
        raise


@contextmanager
def close_on_cancel(
    response: Closable,
    cancel: threading.Event | None,
    deadline: float,
    *,
    active: Callable[[], Closable | None] | None = None,
) -> Iterator[threading.Event]:
    done = threading.Event()
    expired = threading.Event()

    def monitor() -> None:
        while not done.wait(0.02):
            if time.monotonic() >= deadline or cancel is not None and cancel.is_set():
                expired.set()
                # The outer client watcher must also shutdown its active response
                # before close, otherwise it can win the race and only close its fd.
                shutdown_response(active() if active is not None else None)
                shutdown_response(response)
                with suppress(OSError, RuntimeError, httpx.HTTPError):
                    response.close()
                return

    watcher = threading.Thread(target=monitor, name="model-stream-cancel", daemon=True)
    watcher.start()
    try:
        yield expired
    finally:
        done.set()
        response.close()
        watcher.join(timeout=0.1)


class StreamingHTTP(ModelPort):
    """Adapters supply request bodies and parsed events, never error bodies."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider: str,
        caps: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        guard: QuotaGuard | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Model base URL must be an HTTP origin/path without credentials or query")
        self.base_url = base_url.rstrip("/")
        self.api_key, self.model, self.provider = api_key, model, provider
        self.caps, self.settings = caps or {}, dict(settings or {})
        if membership_endpoint(self.base_url, self.provider):
            self.settings["membership"] = True
        validate_model_settings(model, self.settings)
        self.transport, self.sleep, self.max_retries = transport, sleep, max_retries
        self.membership = bool(self.settings.get("membership", False))
        self.guard, self._guard_role = (
            guard,
            self.settings.get("role_binding", "primary"),
        )
        self.request_count = 0
        self.quota_errors = 0

    def assert_role(self, role: str) -> None:
        if self.membership and role != self._guard_role:
            raise ConfigError("会员端口角色已在可信构造时绑定")

    def execution_metadata(self, role: str) -> dict[str, Any]:
        self.assert_role(role)
        return turn_policy(self.model, self.settings, role)

    def _events(
        self,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str],
        parser: Callable[..., Iterator[StreamEvent]],
        cancel: threading.Event | None,
    ) -> Iterator[StreamEvent]:
        check_cancel(cancel)
        deadline = time.monotonic() + float(self.settings.get("total_timeout", 600))
        started, parse_retries = time.monotonic(), 0
        for attempt in range(self.max_retries + 1):
            visible, failure = False, None
            check_cancel(cancel)
            if time.monotonic() >= deadline:
                yield StreamEvent("error", ModelUnavailable())
                return
            try:
                for event in self._request(path, body, headers, parser, cancel, deadline):
                    visible = visible or event.type in {
                        "text",
                        "tool_call",
                        "reasoning",
                    }
                    yield event
                yield StreamEvent(
                    "done",
                    {
                        "model": self.model,
                        "provider": self.provider,
                        "latency_ms": (time.monotonic() - started) * 1000,
                    },
                )
                return
            except ModelQuotaExhausted:
                self.quota_errors += 1
                raise
            except (ModelCancelled, ModelBadRequest):
                raise
            except ModelProtocolError as exc:
                failure = exc
                parse_retries += 1
            except ModelUnavailable as exc:
                failure = exc
            except (httpx.HTTPError, RuntimeError):
                failure = ModelUnavailable()
            except (KeyError, TypeError, AttributeError, ValueError):
                failure = ModelProtocolError()
                parse_retries += 1
            check_cancel(cancel)
            # Retain the mainline cumulative parse budget without bypassing the
            # central action policy or issuing an unguarded physical retry.
            delay = None if parse_retries > 1 else retry_delay(failure, attempt, self.max_retries, visible=visible)
            if delay is None or not wait_for_retry(delay, deadline, cancel, self.sleep):
                check_cancel(cancel)
                yield StreamEvent("error", failure)
                return

    def _request(
        self,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str],
        parser: Callable[..., Iterator[StreamEvent]],
        cancel: threading.Event | None,
        deadline: float,
    ) -> Iterator[StreamEvent]:
        if time.monotonic() >= deadline:
            raise ModelUnavailable()
        timeout = httpx.Timeout(
            float(self.settings.get("first_byte_timeout", 60)),
            connect=float(self.settings.get("connect_timeout", 10)),
        )
        active: list[httpx.Response | None] = [None]
        with (
            httpx.Client(transport=self.transport, timeout=timeout, follow_redirects=False) as client,
            close_on_cancel(client, cancel, deadline, active=lambda: active[0]) as client_expired,
        ):
            check_cancel(cancel)
            request = client.build_request(
                "POST",
                self.base_url + path,
                headers=headers,
                json=sampling_body(body, self.caps),
            )
            check_request_size(request, model=self.model, settings=self.settings)
            check_cancel(cancel)
            if time.monotonic() >= deadline:
                raise ModelUnavailable()
            with (
                provider_attempt(
                    membership=self.membership,
                    role=self._guard_role,
                    provider=self.provider,
                    model=self.model,
                    transport=self.transport,
                    guard=self.guard,
                    cancel_event=cancel,
                    timeout=max(0, min(10, deadline - time.monotonic())),
                ) as attempt,
                cancellation_errors(cancel),
            ):
                before_provider_request()
                before_observed_send()
                self.request_count += 1
                with closing(client.send(request, stream=True)) as response:
                    active[0] = response
                    with (
                        close_on_cancel(response, cancel, deadline) as expired,
                        reset_errors(response.headers),
                    ):
                        if response.status_code != 200:
                            failure = http_error(response, membership=self.membership)
                            check_cancel(cancel)
                            raise failure
                        for event in parser(sse(response, cancel)):
                            check_cancel(cancel)
                            if expired.is_set() or client_expired.is_set() or time.monotonic() >= deadline:
                                raise ModelUnavailable()
                            if event.type == "usage":
                                observe_usage(attempt, event.data)
                            yield event
                        check_cancel(cancel)
                        if expired.is_set() or client_expired.is_set() or time.monotonic() >= deadline:
                            raise ModelUnavailable()

"""HTTP/SSE transport with safe retries, cancellation and a wall-clock deadline."""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from .errors import (
    ModelBadRequest,
    ModelCancelled,
    ModelProtocolError,
    ModelQuotaExhausted,
    ModelRateLimited,
    ModelUnavailable,
)
from .port import ModelPort, StreamEvent


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
    }
    return {
        key: value
        for key, value in (data or {}).items()
        if key in names and type(value) is int and 0 <= value <= 2**63 - 1
    }


def check_cancel(event: threading.Event | None) -> None:
    if event is not None and event.is_set():
        raise ModelCancelled()


def http_error(response: httpx.Response, *, membership: bool) -> ModelUnavailable:
    status = response.status_code
    # Inspect only to classify; this local value is never attached to an exception or logged.
    sample = next(response.iter_bytes(chunk_size=4096), b"").decode("utf-8", errors="ignore").lower()
    quota = any(word in sample for word in ("usage limit", "quota", "额度", "usage_limit"))
    if quota or membership and status == 429:
        return ModelQuotaExhausted(status=status)
    if status == 429:
        return ModelRateLimited(status=status)
    return ModelUnavailable(status=status) if status >= 500 else ModelBadRequest(status=status)


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
    return json.loads(value, parse_constant=_reject_constant)


def stream_error(data: Any, *, membership: bool) -> ModelUnavailable:
    classification = str(data).casefold()
    rate = any(word in classification for word in ("rate_limit", "rate limit", "429"))
    quota = any(word in classification for word in ("quota", "usage_limit", "usage limit", "额度"))
    if quota or membership and rate:
        return ModelQuotaExhausted(status=429 if rate else None)
    return ModelRateLimited(status=429) if rate else ModelUnavailable()


@contextmanager
def close_on_cancel(response: Closable, cancel: threading.Event | None, deadline: float) -> Iterator[threading.Event]:
    done = threading.Event()
    expired = threading.Event()

    def monitor() -> None:
        while not done.wait(0.02):
            if time.monotonic() >= deadline or cancel is not None and cancel.is_set():
                expired.set()
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
        self.caps, self.settings = caps or {}, settings or {}
        self.transport, self.sleep, self.max_retries = transport, sleep, max_retries
        self.membership = bool(self.settings.get("membership", False))
        self.request_count = 0
        self.quota_errors = 0

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
            try:
                for event in self._request(path, body, headers, parser, cancel, deadline):
                    visible = visible or event.type in {"text", "tool_call", "reasoning"}
                    yield event
                yield StreamEvent(
                    "done",
                    {"model": self.model, "provider": self.provider, "latency_ms": (time.monotonic() - started) * 1000},
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
            except httpx.HTTPError:
                failure = ModelUnavailable()
            except (KeyError, TypeError, AttributeError, ValueError):
                failure = ModelProtocolError()
                parse_retries += 1
            check_cancel(cancel)
            if visible or attempt >= self.max_retries or parse_retries > 1 or time.monotonic() >= deadline:
                yield StreamEvent("error", failure)
                return
            delay = (1, 3, 9)[min(attempt, 2)] + random.uniform(0, 0.2)
            if cancel is not None and self.sleep is time.sleep:
                cancel.wait(delay)
            else:
                self.sleep(delay)

    def _request(
        self,
        path: str,
        body: dict[str, Any],
        headers: dict[str, str],
        parser: Callable[..., Iterator[StreamEvent]],
        cancel: threading.Event | None,
        deadline: float,
    ) -> Iterator[StreamEvent]:
        timeout = httpx.Timeout(
            float(self.settings.get("first_byte_timeout", 60)), connect=float(self.settings.get("connect_timeout", 10))
        )
        with (
            httpx.Client(transport=self.transport, timeout=timeout, follow_redirects=False) as client,
            close_on_cancel(client, cancel, deadline) as client_expired,
        ):
            check_cancel(cancel)
            self.request_count += 1
            with (
                client.stream("POST", self.base_url + path, headers=headers, json=body) as response,
                close_on_cancel(response, cancel, deadline) as expired,
            ):
                if response.status_code != 200:
                    raise http_error(response, membership=self.membership)
                for event in parser(sse(response, cancel)):
                    check_cancel(cancel)
                    if expired.is_set() or client_expired.is_set():
                        raise ModelUnavailable()
                    yield event
                check_cancel(cancel)
                if expired.is_set() or client_expired.is_set():
                    raise ModelUnavailable()

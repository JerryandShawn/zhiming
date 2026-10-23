"""Count admitted HTTP attempts without letting provider stops become business answers."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

import httpx

from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.metering import request_meter
from mingjing_core.models.port import ChatMessage, ModelPort, StreamEvent
from mingjing_core.models.quota_delegated_session import require_active
from mingjing_core.models.quota_runtime import current_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.models.registry import ModelHandle, RegistryPort
from tools.eval.quota import STOP_REASONS, ProviderStopped, provider_http_status, provider_stop_reason


class LiveTrackingPort(ModelPort):
    def __init__(self, port: RegistryPort, *, role: str = "target") -> None:
        self.port = port
        self.role = role
        self.calls = self.external_calls = 0
        self.requests: list[dict[str, Any]] = []
        self._substituted = False
        self._turn_calls, self._turn_started = 0, time.perf_counter()
        self._before_send: ContextVar[Callable[[], None] | None] = ContextVar(
            "eval_send_authorization_" + str(id(self)), default=None
        )
        factory = port.factory

        def observe_factory(handle: ModelHandle) -> ModelPort:
            adapter = factory(handle)
            self._substituted = isinstance(getattr(adapter, "transport", None), httpx.MockTransport)
            return adapter

        port.factory = observe_factory

    def begin_turn(self) -> None:
        self._turn_calls, self._turn_started = self.calls, time.perf_counter()

    @contextmanager
    def authorize_before_send(self, authorize: Callable[[], None]) -> Iterator[None]:
        previous = self._before_send.get()

        def combined() -> None:
            if previous is not None:
                previous()
            authorize()

        token = self._before_send.set(combined)
        try:
            yield
        finally:
            self._before_send.reset(token)

    def _before_request(self) -> None:
        # The callback runs after PG admission and immediately before client.send.
        if authorize := self._before_send.get():
            authorize()
        self.calls += 1
        self.external_calls += int(not self._substituted)

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.requests.append({"messages": list(messages)})
        try:
            scope = current_scope()
            if scope.lane != "eval" or not scope.scenario_id:
                raise GuardRejected("manual_start_required")
            if require_active().phase != "core":
                raise GuardRejected("batch_conflict")
            with request_meter(self._before_request):
                yield from self.port.stream(messages, **kwargs)
        except ModelUnavailable as error:
            reason = error.kind if error.kind in STOP_REASONS else provider_stop_reason(error)
            diagnostic = error.safe_diagnostic()
            raise ProviderStopped(
                reason or "provider_http_error",
                self.role,
                model_calls=self.calls - self._turn_calls,
                elapsed_seconds=time.perf_counter() - self._turn_started,
                provider_http_status=provider_http_status(error),
                resume_at=diagnostic.get("resume_at") or diagnostic.get("provider_reset_at"),
            ) from None

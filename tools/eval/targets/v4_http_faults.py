"""Finite offline HTTP faults exercise the real registry and transport policy."""

from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx

from mingjing_core.models.errors import ModelProtocolError, ModelUnavailable
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage, StreamEvent
from mingjing_core.models.registry import ModelHandle, ModelRegistry

from .v4_protocols import wire_output
from .v4_scripted import ScriptedModelPort

MODEL = "synthetic-http-primary"
PROVIDER = "scripted-http-fault"
CONFLICTS = frozenset(
    {"provider_failures", "crash_after", "model_matrix", "critic_scripted", "critic_verdicts", "revoke_after_context"}
)


def fault_port(seed: dict[str, Any], protocol: str | None, *, scripted: bool) -> HttpFaultPort | None:
    controls = seed.get("controls", {})
    if "primary_errors" not in controls:
        return None
    errors = controls["primary_errors"]
    if (
        seed.get("synthetic") is not True
        or scripted is not True
        or protocol is not None
        or set(controls) & CONFLICTS
        or not isinstance(errors, list)
        or not 1 <= len(errors) <= 3
        or any(type(status) is not int or status != 503 for status in errors)
    ):
        raise ValueError("HTTP故障驱动仅接受独立的有限503合成序列")
    return HttpFaultPort(tuple(errors))


def _registry() -> ModelRegistry:
    # This configuration is a codec/policy fixture, never a claim about K3,
    # membership, live capabilities or central authorization.
    config = {
        "version": 1,
        "providers": {
            PROVIDER: {
                "protocol": "openai_compat",
                "base_url": "https://synthetic.invalid/v1",
                "api_key_env": "SYNTHETIC_HTTP_FAULT_KEY",
                "settings": {"membership": False, "total_timeout": 30},
            }
        },
        "models": {
            MODEL: {
                "provider": PROVIDER,
                "model": MODEL,
                "caps": {
                    "status": "synthetic_only",
                    "tools": True,
                    "vision": False,
                    "tool_choice": ["auto", "none"],
                    "reasoning_replay": False,
                },
            }
        },
        "roles": {"primary": [MODEL]},
    }
    with TemporaryDirectory(prefix="v4-http-fault-") as directory:
        path = Path(directory) / "synthetic-models.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return ModelRegistry(path, environment={"SYNTHETIC_HTTP_FAULT_KEY": "synthetic-http-fault-key"})


class _ObservedHTTP(OpenAICompat):
    """Observe already classified errors without replacing any retry behavior."""

    def __init__(self, *, observe: Callable[[ModelUnavailable], None], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.observe = observe

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        for event in super().stream(messages, **kwargs):
            if event.type == "error" and isinstance(event.data, ModelUnavailable):
                self.observe(event.data)
            yield event


class HttpFaultPort(ScriptedModelPort):
    """One logical model step can contain multiple actual MockTransport sends."""

    def __init__(self, errors: tuple[int, ...]) -> None:
        super().__init__()
        self.failures = list(errors)
        self.logical_calls = self.success_actions = 0
        self.current_messages: list[ChatMessage] = []
        self.attempts: list[dict[str, Any]] = []
        self.observed: list[dict[str, Any]] = []
        self.delays: list[float] = []
        self.selected: list[str] = []
        self.adapters: list[OpenAICompat] = []
        self.registry = _registry()
        self.port = self.registry.port(factory=self._adapter)
        self.turn_start = 0

    def _adapter(self, handle: ModelHandle) -> OpenAICompat:
        self.selected.append(handle.model)
        adapter = _ObservedHTTP(
            base_url=handle.base_url,
            api_key=handle.api_key,
            model=handle.model,
            provider=handle.provider,
            caps=handle.caps,
            settings=handle.settings,
            transport=httpx.MockTransport(self._respond),
            sleep=self._sleep,
            max_retries=0,
            observe=self._error,
        )
        self.adapters.append(adapter)
        return adapter

    def _sleep(self, delay: float) -> None:
        self.delays.append(delay)
        time.sleep(delay)

    def _error(self, error: ModelUnavailable) -> None:
        self.observed.append(
            {
                "name": "model.error",
                "source_store": "actual HTTP adapter classified error event",
                "mock_request": self.calls,
                "http_status": error.provider_http_status,
                "kind": error.kind,
                "max_attempts": error.retry_actions.max_attempts,
                "model": self.attempts[-1]["model"],
            }
        )

    def _respond(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or str(request.url) != "https://synthetic.invalid/v1/chat/completions":
            raise ModelProtocolError()
        body = json.loads(request.content)
        if body.get("model") != MODEL:
            raise ModelProtocolError()
        self.calls += 1
        status = self.failures.pop(0) if self.failures else 200
        self.attempts.append(
            {
                "index": self.calls,
                "model": body["model"],
                "http_status": status,
                "pending_actions": len(self.actions),
                "request_sha256": hashlib.sha256(request.content).hexdigest(),
            }
        )
        if status == 503:
            return httpx.Response(503, json={"error": {"type": "api_error", "message": "synthetic transient"}})
        if not self.actions:
            raise ModelProtocolError()
        action = self._value(copy.deepcopy(self.actions.pop(0)), self.current_messages)
        self.success_actions += 1
        return httpx.Response(200, content=wire_output(action, "openai_compat", f"http-fault-{self.calls}"))

    def start(self, *args: Any, **kwargs: Any) -> None:
        super().start(*args, **kwargs)
        self.turn_start = len(self.observed)

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        self.logical_calls += 1
        self.current_messages = messages
        self.requests.append(
            {"messages": copy.deepcopy(messages), "tool_names": [tool.name for tool in kwargs["tools"]]}
        )
        yield from self.port.stream(messages, **kwargs)

    def observations(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self.observed[self.turn_start :])

    def proof(self) -> dict[str, Any]:
        return {
            "scope": "offline nonmembership synthetic model; no K3 or central authorization proof",
            "source_store": "actual RegistryPort + HTTP adapter + MockTransport observations",
            "logical_model_steps": self.logical_calls,
            "mock_http_requests": self.calls,
            "adapter_http_requests": sum(adapter.request_count for adapter in self.adapters),
            "external_provider_requests": 0,
            "selected_models": list(self.selected),
            "attempts": copy.deepcopy(self.attempts),
            "classified_errors": copy.deepcopy(self.observed),
            "retry_delays_seconds": list(self.delays),
            "success_actions_consumed": self.success_actions,
            "pending_actions": len(self.actions),
        }


def fault_evidence(port: Any) -> dict[str, Any]:
    return {"http_faults": port.proof()} if isinstance(port, HttpFaultPort) else {}

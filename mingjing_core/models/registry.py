"""Environment-only credentials, role resolution and request-local failover."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .anthropic_messages import AnthropicMessages
from .errors import (
    ModelBadRequest,
    ModelCancelled,
    ModelQuotaExhausted,
    ModelUnavailable,
)
from .openai_compat import OpenAICompat
from .port import ChatMessage, ModelPort, StreamEvent
from .transport import StreamingHTTP

LOG = logging.getLogger(__name__)
DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config/models.yaml"


@dataclass(frozen=True)
class ModelHandle:
    name: str
    provider: str
    model: str
    protocol: str
    base_url: str
    api_key: str = field(repr=False)
    caps: dict[str, Any]
    settings: dict[str, Any]

    def adapter(self, **kwargs: Any) -> ModelPort:
        adapter = {"openai_compat": OpenAICompat, "anthropic_messages": AnthropicMessages}.get(self.protocol)
        if adapter is None:
            raise ValueError("Unknown model protocol")
        return adapter(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            provider=self.provider,
            caps=self.caps,
            settings=self.settings,
            **kwargs,
        )


class ModelRegistry:
    def __init__(self, path: str | Path | None = None, *, environment: Mapping[str, str] | None = None) -> None:
        self.environment = os.environ if environment is None else environment
        self.path = Path(path or self.environment.get("MODELS_CONFIG") or DEFAULT_CONFIG)
        self.data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        self.warned: set[str] = set()
        if not isinstance(self.data, dict) or self.data.get("version") != 1:
            raise ValueError("Unsupported model registry version")

    def resolve(self, role: str = "primary") -> list[ModelHandle]:
        handles = []
        chain = self.data.get("roles", {}).get(role, [])
        if not isinstance(chain, list):
            return []
        for name in chain:
            entry = self.data["models"][name]
            provider = self.data["providers"][entry["provider"]]
            if not provider.get("enabled", True) or not entry.get("enabled", True):
                continue
            key = self.environment.get(provider["api_key_env"], "")
            if not key and provider.get("api_key_fallback_env"):
                key = self.environment.get(provider["api_key_fallback_env"], "")
            if not key:
                if name not in self.warned:
                    LOG.warning("Model credential missing; skipping configured model %s", name)
                    self.warned.add(name)
                continue
            base = self.environment.get(provider.get("base_url_env", "")) or provider["base_url"]
            model = self.environment.get(entry.get("model_env", "")) or entry["model"]
            handles.append(
                ModelHandle(
                    name,
                    entry["provider"],
                    model,
                    provider["protocol"],
                    base,
                    key,
                    dict(entry.get("caps", {})),
                    {**provider.get("settings", {}), **entry.get("settings", {})},
                )
            )
        return handles

    def port(self, role: str = "primary", **kwargs: Any) -> RegistryPort:
        return RegistryPort(self, role=role, **kwargs)


class RegistryPort(ModelPort):
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        role: str = "primary",
        factory: Callable[[ModelHandle], ModelPort] | None = None,
        stop_on_quota: bool = False,
        total_timeout: float | None = None,
    ) -> None:
        self.registry, self.role = registry, role
        # Registry makes two attempts per provider; adapters must not multiply this budget.
        self.factory = factory or (lambda handle: handle.adapter(max_retries=0))
        self.stop_on_quota = stop_on_quota
        self.total_timeout = total_timeout
        self.quota_errors = 0

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        role = kwargs.pop("role", self.role)
        blocked_memberships: set[str] = set()
        last: ModelUnavailable = ModelUnavailable()
        handles = self.registry.resolve(role)
        timeout = (
            self.total_timeout
            if self.total_timeout is not None
            else (float(handles[0].settings.get("total_timeout", 600)) if handles else 600)
        )
        deadline = time.monotonic() + timeout
        for handle in handles:
            if handle.api_key in blocked_memberships:
                continue
            adapter = self.factory(handle)
            for _ in range(2):
                visible = False
                try:
                    for event in self._attempt(adapter, messages, deadline, role=role, **kwargs):
                        if event.type == "error":
                            raise event.data
                        visible = visible or event.type in {"text", "reasoning", "tool_call"}
                        yield event
                    return
                except ModelQuotaExhausted as exc:
                    self.quota_errors += 1
                    last = exc
                    if self.stop_on_quota or visible:
                        raise
                    blocked_memberships.add(handle.api_key)
                    break
                except (ModelBadRequest, ModelCancelled):
                    raise
                except ModelUnavailable as exc:
                    last = exc
                    if visible:
                        raise
        raise last

    def _attempt(
        self, adapter: ModelPort, messages: list[ChatMessage], deadline: float, **kwargs: Any
    ) -> Iterator[StreamEvent]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ModelUnavailable()
        settings = adapter.settings if isinstance(adapter, StreamingHTTP) else None
        if settings is not None:
            adapter.settings = {**settings, "total_timeout": min(float(settings.get("total_timeout", 600)), remaining)}
        try:
            yield from adapter.stream(messages, **kwargs)
        finally:
            if settings is not None:
                adapter.settings = settings

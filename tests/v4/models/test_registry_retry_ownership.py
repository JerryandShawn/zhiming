"""Injected HTTP adapters cannot multiply the registry's physical retry budget."""

from __future__ import annotations

import threading
from pathlib import Path

import httpx
import pytest

from mingjing_core.models.errors import ModelCancelled, ModelUnavailable
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.registry import ModelHandle, RegistryPort

from .test_protocols import recording
from .test_schema_registry import registry as fixture_registry


def _probe(
    tmp_path: Path, statuses: list[int], cancel: threading.Event | None = None
) -> tuple[RegistryPort, list[OpenAICompat], list[int], list[float]]:
    registry = fixture_registry(tmp_path)
    registry.data["roles"]["primary"] = ["a"]
    adapters: list[OpenAICompat] = []
    requests: list[int] = []
    delays: list[float] = []

    def sleep(delay: float) -> None:
        delays.append(delay)
        if cancel is not None:
            cancel.set()

    def factory(handle: ModelHandle) -> OpenAICompat:
        def respond(_: httpx.Request) -> httpx.Response:
            status = statuses[min(len(requests), len(statuses) - 1)]
            requests.append(status)
            content = recording({"choices": [{"delta": {"content": "合成成功"}, "finish_reason": "stop"}]})
            return httpx.Response(status, content=content if status == 200 else b"")

        # A supported custom factory may leave the direct adapter retry default on.
        model = OpenAICompat(
            base_url=handle.base_url,
            api_key=handle.api_key,
            model=handle.model,
            provider=handle.provider,
            caps=handle.caps,
            settings=handle.settings,
            transport=httpx.MockTransport(respond),
            sleep=sleep,
            max_retries=3,
        )
        adapters.append(model)
        return model

    return registry.port(factory=factory), adapters, requests, delays


def test_registry_owns_retry_budget_for_injected_retrying_adapter(tmp_path: Path) -> None:
    # This factory reproduced 16 HTTP attempts before registry-only retry ownership.
    port, adapters, requests, delays = _probe(tmp_path, [503])
    with pytest.raises(ModelUnavailable):
        port.complete([])
    assert requests == [503] * 4
    assert len(delays) == 3
    assert len(adapters) == 1 and adapters[0].max_retries == 3


def test_registry_restores_adapter_retry_setting_after_success(tmp_path: Path) -> None:
    port, adapters, requests, delays = _probe(tmp_path, [503, 200])
    result = port.complete([])
    assert result.text == "合成成功"
    assert requests == [503, 200] and len(delays) == 1
    assert len(adapters) == 1 and adapters[0].max_retries == 3


def test_registry_restores_adapter_retry_setting_after_cancel(tmp_path: Path) -> None:
    cancel = threading.Event()
    port, adapters, requests, delays = _probe(tmp_path, [503], cancel)
    with pytest.raises(ModelCancelled):
        port.complete([], cancel_event=cancel)
    assert requests == [503] and len(delays) == 1
    assert len(adapters) == 1 and adapters[0].max_retries == 3

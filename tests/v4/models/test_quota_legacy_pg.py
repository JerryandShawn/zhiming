"""The retained v3 adapter keeps its body/parser while real PG gates its HTTP."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository

from .test_quota_guard_pg import configure_central
from .test_quota_http_pg import rows


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def client_substitute(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    original = httpx.Client
    monkeypatch.setattr(
        "mingjing_core.adapters.model.httpx.Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(handler),
            **kwargs,
        ),
    )


def test_legacy_success_is_recorded_in_same_central_account(
    central: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = QuotaGuard(**central)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "submit", "input": {"value": "synthetic"}}],
                "usage": {"input_tokens": 9, "output_tokens": 2},
                "stop_reason": "tool_use",
            },
        )

    client_substitute(monkeypatch, handler)
    model = ConfiguredModel(
        key="synthetic", base="https://api.kimi.com/coding/v1", model="k3", guard=guard, role="critic"
    )
    result = model.generate(system="synthetic", payload={}, schema={}, purpose="review")
    assert result["output"] == {"value": "synthetic"} and len(requests) == 1
    assert (rows(guard)[0]["role"], rows(guard)[0]["bucket"], rows(guard)[0]["input_tokens"]) == ("critic", "critic", 9)
    assert guard.status()["in_flight"] == 0
    wire = json.loads(requests[0].content)
    assert wire["model"] == "k3"  # Explicit historical identity was not silently renamed.
    assert "thinking" not in wire and "temperature" not in wire
    assert wire["tool_choice"] == {"type": "any", "disable_parallel_tool_use": True}


@pytest.mark.parametrize(
    "message,kind",
    [
        ("Too many concurrent requests", "concurrency_limited"),
        ("Access terminated", "access_terminated"),
    ],
)
def test_legacy_terminal_error_stops_new_and_legacy_callers(
    central: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    message: str,
    kind: str,
) -> None:
    guard = QuotaGuard(**central)
    sent = []

    def handler(_: httpx.Request) -> httpx.Response:
        sent.append(1)
        return httpx.Response(403, json={"error": {"type": "permission_error", "message": message}})

    client_substitute(monkeypatch, handler)
    model = ConfiguredModel(key="synthetic", base="https://api.kimi.com/coding/v1", model="k3", guard=guard)
    for _ in range(2):
        with pytest.raises(ModelUnavailable):
            model.generate(system="synthetic", payload={}, schema={}, purpose="intake")
    assert sent == [1] and rows(guard)[0]["status"] == kind
    assert guard.status()["stop_kind"] == kind and guard.status()["in_flight"] == 0

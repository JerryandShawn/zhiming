"""HTTP retries consume a single budget and never replay visible private output."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage
from tools.eval.quota import provider_stop_reason

from .test_protocols import adapter, recording
from .test_schema_registry import registry

MATRIX = json.loads(
    (Path(__file__).resolve().parents[3] / "tools/eval/fixtures/u37_error_matrix.json").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", MATRIX, ids=lambda row: row["id"])
def test_matrix_reaches_real_http_sse_adapter_boundary(case: dict[str, Any]) -> None:
    entry, expected = case["input"], case["expected"]

    def respond(_: httpx.Request) -> httpx.Response:
        if entry["surface"] == "http":
            return httpx.Response(entry["status"], json=entry["body"])
        return httpx.Response(200, content=recording({**entry["body"], "type": "error"}))

    model = adapter(
        respond,
        AnthropicMessages if entry["surface"] == "sse" else OpenAICompat,
        settings={"membership": entry["membership"]},
        max_retries=0,
    )
    with pytest.raises(ModelUnavailable) as caught:
        model.complete([])
    assert caught.value.kind == expected["kind"]
    assert caught.value.provider_http_status == entry["status"]
    assert model.request_count == 1
    public = json.dumps(caught.value.safe_diagnostic(), ensure_ascii=False) + str(caught.value)
    assert all(marker not in public for marker in expected["never_include"])


@pytest.mark.parametrize(
    "status,kind,attempts,bases", [(402, "membership_unverified", 2, [60]), (429, "rate_limited", 4, [1, 3, 9])]
)
def test_direct_adapter_has_one_retry_policy(status: int, kind: str, attempts: int, bases: list[int]) -> None:
    delays: list[float] = []
    model = adapter(lambda _: httpx.Response(status), settings={"membership": True})
    model.sleep = delays.append
    with pytest.raises(ModelUnavailable) as caught:
        model.complete([])
    assert caught.value.kind == kind and model.request_count == attempts
    assert len(delays) == len(bases)
    for delay, base in zip(delays, bases, strict=True):
        assert base <= delay <= base + (0 if status == 402 else 0.2)
    assert model.quota_errors == 0
    assert provider_stop_reason(caught.value) == "provider_http_error"


@pytest.mark.parametrize("status,kind", [(402, "membership_unverified"), (429, "rate_limited"), (503, "unavailable")])
def test_registry_does_not_multiply_adapter_retry_budget(tmp_path: Any, status: int, kind: str) -> None:
    reg = registry(tmp_path)
    reg.data["roles"]["primary"] = ["a"]
    requests: list[str] = []
    delays: list[float] = []

    def factory(handle: Any) -> Any:
        def respond(_: httpx.Request) -> httpx.Response:
            requests.append(handle.model)
            return httpx.Response(status)

        model = adapter(respond, max_retries=0, settings={"membership": True})
        model.sleep = delays.append
        return model

    with pytest.raises(ModelUnavailable) as caught:
        reg.port(factory=factory).complete([])
    assert caught.value.kind == kind
    assert len(requests) == (2 if status == 402 else 4)
    assert len(delays) == len(requests) - 1


@pytest.mark.parametrize(
    "message,kind",
    [("Too many concurrent requests", "concurrency_limited"), ("Access terminated", "access_terminated")],
)
def test_global_stop_is_not_retried_or_routed_to_sibling(tmp_path: Any, message: str, kind: str) -> None:
    reg = registry(tmp_path)
    requests: list[str] = []

    def factory(handle: Any) -> Any:
        def respond(_: httpx.Request) -> httpx.Response:
            requests.append(handle.model)
            return httpx.Response(403, json={"error": {"type": "permission_error", "message": message}})

        return adapter(respond, max_retries=0, settings={"membership": True})

    with pytest.raises(ModelUnavailable) as caught:
        reg.port(factory=factory).complete([])
    assert caught.value.kind == kind and caught.value.global_stop
    assert requests == ["a"]
    assert provider_stop_reason(caught.value) == kind


def test_visible_sse_failure_cannot_fallback_or_retry(tmp_path: Any) -> None:
    reg = registry(tmp_path)
    requests: list[str] = []

    def factory(handle: Any) -> Any:
        def respond(_: httpx.Request) -> httpx.Response:
            requests.append(handle.model)
            return httpx.Response(
                200,
                content=recording(
                    {"choices": [{"delta": {"content": "合成部分回答"}}]},
                    {"error": {"type": "rate_limit_error", "message": "synthetic-private"}},
                ),
            )

        return adapter(respond, max_retries=0, settings={"membership": True})

    events: list[str] = []
    with pytest.raises(ModelUnavailable) as caught:
        for event in reg.port(factory=factory).stream([]):
            events.append(event.type)
    assert events == ["text"] and requests == ["a"]
    assert "private" not in json.dumps(caught.value.safe_diagnostic())


def test_unknown_sse_error_has_no_invented_http_status_or_retry() -> None:
    body = recording({"error": {"type": "unrecognized", "message": "quota 429 synthetic-private"}})
    model = adapter(lambda _: httpx.Response(200, content=body), settings={"membership": True})
    with pytest.raises(ModelUnavailable) as caught:
        model.complete([])
    assert model.request_count == 1 and caught.value.provider_http_status is None
    assert caught.value.kind == "unavailable" and caught.value.retry_actions.retry == "never"
    assert "private" not in str(caught.value.safe_diagnostic())


def test_cancel_during_membership_wait_prevents_second_post() -> None:
    cancel = threading.Event()
    model = adapter(lambda _: httpx.Response(402), settings={"membership": True})
    model.sleep = lambda _: cancel.set()
    with pytest.raises(ModelUnavailable) as caught:
        model.complete([ChatMessage("user", "合成")], cancel_event=cancel)
    assert caught.value.kind == "cancelled" and model.request_count == 1

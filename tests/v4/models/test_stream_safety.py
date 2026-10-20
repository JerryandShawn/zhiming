"""Malformed provider data and cancellation cannot bypass quota/privacy guards."""

import json
import threading
import time
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.anthropic_messages import encode_messages as anthropic_encode
from mingjing_core.models.errors import (
    CapabilityError,
    ModelBadRequest,
    ModelCancelled,
    ModelProtocolError,
    ModelRateLimited,
    ModelUnavailable,
)
from mingjing_core.models.openai_compat import OpenAICompat, encode_messages
from mingjing_core.models.port import ChatMessage, Part
from mingjing_core.models.transport import safe_usage

from .test_protocols import CAPS, adapter, openai_record, recording


def test_untagged_reasoning_is_never_replayed() -> None:
    messages = [ChatMessage("assistant", "答复", reasoning="unscoped", reasoning_signature="signature")]
    assert "reasoning_content" not in encode_messages(messages, CAPS)[0]
    _, rows = anthropic_encode(messages, CAPS)
    assert all(part["type"] != "thinking" for part in rows[0]["content"])


@pytest.mark.parametrize("protocol", [None, AnthropicMessages])
def test_streamed_membership_rate_limit_uses_bounded_backoff(protocol: Any) -> None:
    data = recording({"type": "error", "error": {"type": "rate_limit_error", "message": "synthetic-private"}})
    kwargs = {"settings": {"membership": True}}
    model = (
        adapter(lambda _: httpx.Response(200, content=data), protocol, **kwargs)
        if protocol
        else adapter(lambda _: httpx.Response(200, content=data), **kwargs)
    )
    with pytest.raises(ModelRateLimited) as caught:
        model.complete([ChatMessage("user", "查询")])
    assert model.request_count == 4 and model.quota_errors == 0
    assert "private" not in str(caught.value.safe_diagnostic())


@pytest.mark.parametrize(
    "arguments", ['{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e9999}', '{"x":[-1e9999]}']
)
def test_nonfinite_tool_json_is_rejected(arguments: str) -> None:
    model = adapter(lambda _: httpx.Response(200, content=openai_record(arguments)), max_retries=0)
    with pytest.raises(ModelProtocolError):
        model.complete([])


@pytest.mark.parametrize("usage", [None, [], "private", 5])
def test_malformed_usage_cannot_escape_safe_parser(usage: Any) -> None:
    assert safe_usage(usage) == {}


def test_total_deadline_and_cancel_close_transport_while_waiting_headers() -> None:
    class BlockingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = threading.Event()

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.closed.wait(2)
            raise httpx.ReadTimeout("synthetic-private")

        def close(self) -> None:
            self.closed.set()

    for cancellation in (True, False):
        transport = BlockingTransport()
        event = threading.Event()
        timer = threading.Timer(0.04, event.set)
        if cancellation:
            timer.start()
        model = OpenAICompat(
            base_url="https://synthetic.invalid",
            api_key="synthetic",
            model="test",
            provider="test",
            caps=CAPS,
            transport=transport,
            max_retries=0,
            settings={"total_timeout": 0.08},
        )
        started = time.monotonic()
        with pytest.raises(ModelCancelled if cancellation else ModelUnavailable):
            model.complete([], cancel_event=event)
        timer.cancel()
        assert time.monotonic() - started < 0.6 and transport.closed.is_set()


def test_incomplete_anthropic_tool_block_is_not_committed() -> None:
    data = recording(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": "x", "name": "lookup", "input": {}},
        },
        {"type": "message_stop"},
    )
    model = adapter(lambda _: httpx.Response(200, content=data), AnthropicMessages, max_retries=0)
    with pytest.raises(ModelProtocolError):
        model.complete([])


@pytest.mark.parametrize(
    "url", ["https://name:synthetic-private@example.invalid", "https://example.invalid?key=x", "bad"]
)
def test_base_url_rejects_credential_and_query(url: str) -> None:
    with pytest.raises(ValueError) as caught:
        OpenAICompat(base_url=url, api_key="synthetic", model="test", provider="test")
    assert "private" not in str(caught.value)


def test_transient_retry_uses_one_three_nine_second_schedule() -> None:
    delays: list[float] = []
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) < 4:
            return httpx.Response(503, text="transient")
        return httpx.Response(
            200, content=recording({"choices": [{"delta": {"content": "成功"}, "finish_reason": "stop"}]})
        )

    model = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="test",
        provider="test",
        transport=httpx.MockTransport(respond),
        sleep=delays.append,
    )
    assert model.complete([]).text == "成功" and model.request_count == 4
    assert len(delays) == 3 and all(
        base <= actual <= base + 0.2 for base, actual in zip((1, 3, 9), delays, strict=True)
    )


def test_cancellation_interrupts_default_backoff_before_second_request() -> None:
    event = threading.Event()
    timer = threading.Timer(0.03, event.set)

    def respond(_: httpx.Request) -> httpx.Response:
        timer.start()
        return httpx.Response(503, text="transient")

    model = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="test",
        provider="test",
        transport=httpx.MockTransport(respond),
    )
    started = time.monotonic()
    try:
        with pytest.raises(ModelCancelled):
            model.complete([], cancel_event=event)
    finally:
        timer.cancel()
    assert time.monotonic() - started < 0.6 and model.request_count == 1


def test_total_deadline_is_checked_after_backoff_before_any_second_post() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return (
            httpx.Response(503)
            if len(requests) == 1
            else httpx.Response(
                200, content=recording({"choices": [{"delta": {"content": "too late"}, "finish_reason": "stop"}]})
            )
        )

    model = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="test",
        provider="test",
        transport=httpx.MockTransport(respond),
        sleep=lambda _: time.sleep(0.03),
        settings={"total_timeout": 0.01},
    )
    with pytest.raises(ModelUnavailable):
        model.complete([])
    assert model.request_count == len(requests) == 1


def test_new_real_user_turn_closes_old_tagged_reasoning_cycle() -> None:
    messages = [
        ChatMessage("user", "旧问题"),
        ChatMessage(
            "assistant", "旧答复", reasoning="old-cycle", reasoning_signature="signature", tool_cycle="finished"
        ),
        ChatMessage("user", "新问题"),
    ]
    assert "reasoning_content" not in encode_messages(messages, CAPS)[1]
    _, rows = anthropic_encode(messages, CAPS)
    assert all(part["type"] != "thinking" for part in rows[1]["content"])


def test_anthropic_tool_result_part_list_is_wire_json_and_checks_vision() -> None:
    messages = [ChatMessage("tool", [Part(text="合成结果"), Part(type="image", data="aGVsbG8=")], tool_call_id="call")]
    _, encoded = anthropic_encode(messages, CAPS)
    result = encoded[0]["content"][0]
    assert result["content"][0] == {"type": "text", "text": "合成结果"}
    assert result["content"][1]["source"]["type"] == "base64"
    json.dumps(encoded)

    with pytest.raises(CapabilityError):
        anthropic_encode(messages, {"vision": False})


@pytest.mark.parametrize("status,error", [(429, ModelRateLimited), (401, ModelBadRequest)])
def test_unreadable_error_body_cannot_change_known_membership_status(status: int, error: Any) -> None:
    class BrokenBody(httpx.SyncByteStream):
        def __iter__(self) -> Any:
            raise httpx.ReadError("synthetic-private")

    model = adapter(lambda _: httpx.Response(status, stream=BrokenBody()), settings={"membership": True})
    with pytest.raises(error):
        model.complete([])
    assert model.request_count == (4 if status == 429 else 1)
    assert model.quota_errors == 0

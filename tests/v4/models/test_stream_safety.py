"""Malformed provider data and cancellation cannot bypass quota/privacy guards."""

import threading
import time
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.anthropic_messages import encode_messages as anthropic_encode
from mingjing_core.models.errors import ModelCancelled, ModelProtocolError, ModelQuotaExhausted, ModelUnavailable
from mingjing_core.models.openai_compat import OpenAICompat, encode_messages
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.transport import safe_usage

from .test_protocols import CAPS, adapter, openai_record, recording


def test_untagged_reasoning_is_never_replayed() -> None:
    messages = [ChatMessage("assistant", "答复", reasoning="unscoped", reasoning_signature="signature")]
    assert "reasoning_content" not in encode_messages(messages, CAPS)[0]
    _, rows = anthropic_encode(messages, CAPS)
    assert all(part["type"] != "thinking" for part in rows[0]["content"])


@pytest.mark.parametrize("protocol", [None, AnthropicMessages])
def test_streamed_membership_rate_limit_stops_after_one_request(protocol: Any) -> None:
    data = recording({"type": "error", "error": {"type": "rate_limit_error", "message": "synthetic-private"}})
    kwargs = {"settings": {"membership": True}}
    model = (
        adapter(lambda _: httpx.Response(200, content=data), protocol, **kwargs)
        if protocol
        else adapter(lambda _: httpx.Response(200, content=data), **kwargs)
    )
    with pytest.raises(ModelQuotaExhausted) as caught:
        model.complete([ChatMessage("user", "查询")])
    assert model.request_count == 1 and model.quota_errors == 1
    assert "private" not in str(caught.value.safe_diagnostic())


@pytest.mark.parametrize("arguments", ['{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}'])
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

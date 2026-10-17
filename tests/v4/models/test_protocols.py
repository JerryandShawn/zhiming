"""Synthetic wire recordings exercise both protocols without network access."""

import json
import threading

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.anthropic_messages import (
    encode_messages as anthropic_messages,
)
from mingjing_core.models.errors import (
    CapabilityError,
    ModelBadRequest,
    ModelCancelled,
    ModelProtocolError,
    ModelQuotaExhausted,
    ModelRateLimited,
    ModelUnavailable,
)
from mingjing_core.models.openai_compat import OpenAICompat, encode_messages
from mingjing_core.models.port import ChatMessage, Part, ToolCall, ToolSpec

CAPS = {
    "tools": True,
    "vision": True,
    "tool_choice": ["auto", "none", "required", "named"],
    "include_usage": True,
    "reasoning_field": "reasoning_content",
    "reasoning_replay": True,
}
TOOL = ToolSpec("lookup", "查询合成日期", {"type": "object", "properties": {"day": {"type": "string"}}})


def recording(*chunks: dict) -> bytes:
    return "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks).encode()


def openai_record(arguments: str = '{"day":"周六"}') -> bytes:
    return recording(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "call-1", "function": {"name": "lookup", "arguments": arguments[:5]}}
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": arguments[5:]}}]}}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}], "usage": {"prompt_tokens": 3}},
    )


def adapter(handler, cls=OpenAICompat, **kwargs):
    return cls(
        base_url="https://synthetic.invalid/v1",
        api_key="synthetic-test-key",
        model="test-model",
        provider="synthetic",
        caps=CAPS,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
        **kwargs,
    )


def test_split_tool_json_and_usage():
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert request.headers["User-Agent"] == "MingjingCore/3.0"
        return httpx.Response(200, content=openai_record())

    model = adapter(respond)
    result = model.complete([ChatMessage("user", "周几？")], tools=[TOOL], tool_choice="lookup")
    assert result.tool_calls == [ToolCall("call-1", "lookup", {"day": "周六"})]
    assert result.usage == {"prompt_tokens": 3}
    assert result.model == "test-model" and result.provider == "synthetic"
    assert requests[0]["tool_choice"]["function"]["name"] == "lookup"
    assert requests[0]["stream_options"] == {"include_usage": True}


def test_parallel_calls_assembled_by_index():
    data = recording(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 1, "id": "b", "function": {"name": "lookup", "arguments": '{"day":"二"}'}},
                            {"index": 0, "id": "a", "function": {"name": "lookup", "arguments": '{"day":"一"}'}},
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )
    result = adapter(lambda _: httpx.Response(200, content=data)).complete([ChatMessage("user", "查询")])
    assert [item.id for item in result.tool_calls] == ["a", "b"]


def test_reasoning_replayed_only_for_tagged_active_cycle():
    messages = [
        ChatMessage("assistant", "旧", reasoning="old", tool_cycle="old"),
        ChatMessage("user", "新"),
        ChatMessage("assistant", "", reasoning="current", tool_cycle="new"),
    ]
    encoded = encode_messages(messages, CAPS)
    assert "reasoning_content" not in encoded[0]
    assert encoded[-1]["reasoning_content"] == "current"
    assert "reasoning_content" not in encode_messages(messages, {**CAPS, "reasoning_replay": False})[-1]


def test_text_reasoning_and_caller_tool_roundtrip_l01():
    bodies = []

    def respond(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(200, content=openai_record())
        return httpx.Response(
            200, content=recording({"choices": [{"delta": {"content": "合成周六"}, "finish_reason": "stop"}]})
        )

    model = adapter(respond)
    history = [ChatMessage("user", "查询周几")]
    first = model.complete(history, tools=[TOOL])
    history.extend(
        [first.as_chat(tool_cycle="L01"), ChatMessage("tool", "周六", tool_call_id="call-1", tool_cycle="L01")]
    )
    second = model.complete(history, tools=[TOOL])
    assert second.text == "合成周六"
    assert bodies[1]["messages"][-1]["tool_call_id"] == "call-1"


@pytest.mark.parametrize(
    "status,error,retries",
    [(400, ModelBadRequest, 0), (401, ModelBadRequest, 0), (429, ModelRateLimited, 3), (503, ModelUnavailable, 3)],
)
def test_http_status_retry_budget(status, error, retries):
    model = adapter(lambda _: httpx.Response(status, text="synthetic-private-response"))
    with pytest.raises(error) as caught:
        model.complete([ChatMessage("user", "synthetic-private-user")])
    assert model.request_count == retries + 1
    assert "private" not in str(caught.value) + str(caught.value.safe_diagnostic())
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("status,body", [(429, "rate"), (403, "usage limit"), (500, "quota")])
def test_membership_quota_never_retry(status, body):
    model = adapter(lambda _: httpx.Response(status, text=body), settings={"membership": True})
    with pytest.raises(ModelQuotaExhausted):
        model.complete([ChatMessage("user", "查询")])
    assert model.request_count == model.quota_errors == 1


def test_bad_tool_arguments_retried_once_then_error_event():
    model = adapter(lambda _: httpx.Response(200, content=openai_record("{bad")))
    events = list(model.stream([ChatMessage("user", "查询")]))
    assert events[-1].type == "error" and isinstance(events[-1].data, ModelProtocolError)
    assert model.request_count == 2


def test_cancel_before_request_and_during_stream():
    cancelled = threading.Event()
    cancelled.set()
    model = adapter(lambda _: pytest.fail("cancelled request must not be sent"))
    with pytest.raises(ModelCancelled):
        model.complete([ChatMessage("user", "查询")], cancel_event=cancelled)
    assert model.request_count == 0
    cancelled.clear()

    class RecordingStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield recording({"choices": [{"delta": {"content": "首字"}}]})
            cancelled.set()
            yield b"data: [DONE]\n\n"

        def close(self):
            self.closed = True

    stream = RecordingStream()
    model = adapter(lambda _: httpx.Response(200, stream=stream))
    with pytest.raises(ModelCancelled):
        model.complete([ChatMessage("user", "查询")], cancel_event=cancelled)
    assert stream.closed and model.request_count == 1


def test_image_caps_and_data_uri():
    messages = [ChatMessage("user", [Part(type="image", data="aGVsbG8=", mime="image/png")])]
    assert encode_messages(messages, CAPS)[0]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    with pytest.raises(CapabilityError):
        encode_messages(messages, {})


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_exceptions_are_safe_and_retried(failure):
    def respond(_):
        raise failure("synthetic-private-request")

    model = adapter(respond, max_retries=1)
    with pytest.raises(ModelUnavailable) as caught:
        model.complete([ChatMessage("user", "查询")])
    assert model.request_count == 2 and "private" not in str(caught.value)


def anthropic_record():
    return recording(
        {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "合成推理"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "signature"}},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "call-1", "name": "lookup", "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"day":"周六"}'},
        },
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 7}},
        {"type": "message_stop"},
    )


def test_anthropic_tools_thinking_signature_and_multiturn():
    bodies = []

    def respond(request):
        assert request.url.path == "/v1/messages"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, content=anthropic_record())

    model = adapter(respond, AnthropicMessages, settings={"thinking": {"type": "enabled", "budget_tokens": 1024}})
    result = model.complete([ChatMessage("system", "合成系统"), ChatMessage("user", "查询")], tools=[TOOL])
    assert result.reasoning == "合成推理" and result.reasoning_signature == "signature"
    assert result.usage == {"input_tokens": 5, "output_tokens": 7}
    assert result.tool_calls[0].arguments == {"day": "周六"}
    history = [
        result.as_chat(tool_cycle="cycle"),
        ChatMessage("tool", "周六", tool_call_id="call-1", tool_cycle="cycle"),
    ]
    _, encoded = anthropic_messages(history, CAPS)
    assert encoded[0]["content"][0]["signature"] == "signature"
    assert encoded[1]["content"][0]["type"] == "tool_result"
    assert bodies[0]["thinking"]["budget_tokens"] == 1024


@pytest.mark.parametrize(
    "data,error",
    [
        (recording({"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}), ModelProtocolError),
        (recording({"type": "error", "error": {"message": "quota"}}), ModelQuotaExhausted),
        (b"data: invalid-json\n\n", ModelProtocolError),
    ],
)
def test_anthropic_rejects_incomplete_or_quota_stream(data, error):
    model = adapter(lambda _: httpx.Response(200, content=data), AnthropicMessages, max_retries=0)
    with pytest.raises(error):
        model.complete([ChatMessage("user", "查询")])


def test_no_replay_after_visible_text_failure():
    data = recording({"choices": [{"delta": {"content": "已展示"}}]})
    model = adapter(lambda _: httpx.Response(200, content=data))
    events = list(model.stream([ChatMessage("user", "查询")]))
    assert [event.type for event in events] == ["text", "error"]
    assert model.request_count == 1

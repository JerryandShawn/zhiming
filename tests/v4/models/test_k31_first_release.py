"""R16 synthetic native-wire checks; no account entitlement or live-model proof."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.errors import ModelResponseIdentityError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage
from mingjing_core.models.registry import ModelRegistry
from tools.eval.quota import provider_stop_reason

from .test_protocols import TOOL, recording

PROFILE = Path(__file__).resolve().parents[3] / "config/models.first-release.yaml"


def registry() -> ModelRegistry:
    return ModelRegistry(PROFILE, environment={"KIMI_API_KEY": "synthetic-k31-only"})


def tool_reply() -> bytes:
    return recording(
        {"model": "k3.1-pro", "choices": [{"delta": {"reasoning_content": "合成完整推理"}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "original-opaque",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"day":"周六"}',
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 5},
        },
    )


@pytest.mark.parametrize("role", ["primary", "critic"])
def test_explicit_profile_high_and_original_reasoning_replay_use_actual_native_wire(role: str) -> None:
    reg, requests = registry(), []
    handle = reg.resolve(role)[0]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        content = (
            tool_reply()
            if len(requests) == 1
            else recording(
                {
                    "model": "k3.1-pro",
                    "choices": [{"delta": {"content": "合成长回答。" * 2000}, "finish_reason": "stop"}],
                }
            )
        )
        return httpx.Response(200, content=content)

    port = handle.adapter(transport=httpx.MockTransport(respond), sleep=lambda _: None)
    first = port.complete([ChatMessage("user", "合成问题")], role=role, tools=[TOOL], temperature=0.2)
    second = port.complete(
        [
            ChatMessage("user", "合成问题"),
            first.as_chat(tool_cycle="same-question"),
            ChatMessage("tool", "合成结果", tool_call_id=first.tool_calls[0].id, tool_cycle="same-question"),
        ],
        role=role,
        tools=[TOOL],
    )
    assert isinstance(port, OpenAICompat) and len(requests) == 2
    assert second.text == "合成长回答。" * 2000
    assert first.model == "k3.1-pro" and first.usage == {"prompt_tokens": 9, "completion_tokens": 5}
    assert first.reasoning == "合成完整推理" and first.tool_calls[0].id == "original-opaque"
    assert first.execution_meta["effort_source"] == "explicit_request"
    assert first.execution_meta["effort_verified"] is False
    for request in requests:
        body = json.loads(request.content)
        assert str(request.url) == "https://api.kimi.com/coding/v1/chat/completions"
        assert body["model"] == "k3.1-pro" and body["reasoning_effort"] == "high"
        assert body["tool_choice"] == "required" and "thinking" not in body and "temperature" not in body
    replay = json.loads(requests[1].content)["messages"][1]
    assert replay["reasoning_content"] == first.reasoning
    assert replay["tool_calls"][0]["id"] == first.tool_calls[0].id
    assert ModelRegistry(environment={}).data["models"]["kimi-code-main"]["model"] == "k3-256k"


@pytest.mark.parametrize("returned_model", ["k3", "k3.1-pro-highspeed", "", None])
def test_missing_or_wrong_response_identity_stops_registry_before_content_or_retry(returned_model: Any) -> None:
    reg, requests, events = registry(), [], []
    reg.data["roles"]["primary"].append("kimi-critic")

    def factory(handle):
        def respond(request):
            requests.append(request)
            chunk = {"choices": [{"delta": {"content": "PRIVATE_UNTRUSTED"}, "finish_reason": "stop"}]}
            if returned_model is not None:
                chunk["model"] = returned_model
            return httpx.Response(200, content=recording(chunk))

        return handle.adapter(transport=httpx.MockTransport(respond), sleep=lambda _: pytest.fail("identity retry"))

    with pytest.raises(ModelResponseIdentityError) as caught:
        events.extend(reg.port(factory=factory).stream([]))
    assert len(requests) == 1 and events == []
    assert caught.value.global_stop and caught.value.retry_actions.fallback == "none"
    assert provider_stop_reason(caught.value) == "provider_http_error"
    assert "PRIVATE_UNTRUSTED" not in str(caught.value.safe_diagnostic())


def test_later_response_identity_change_and_empty_response_are_not_protocol_retries() -> None:
    reg = registry()
    for content in (
        b"data: [DONE]\n\n",
        recording(
            {"model": "k3.1-pro", "choices": []},
            {"model": "k3", "choices": [{"delta": {"reasoning_content": "PRIVATE_UNTRUSTED"}}]},
        ),
    ):
        requests = []

        def respond(request, requests=requests, content=content):
            requests.append(request)
            return httpx.Response(200, content=content)

        port = reg.resolve()[0].adapter(transport=httpx.MockTransport(respond), sleep=lambda _: pytest.fail("retry"))
        events = []
        with pytest.raises(ModelResponseIdentityError):
            events.extend(port.stream([]))
        assert events == [] and len(requests) == 1


def test_k31_missing_high_or_unsupported_anthropic_path_fail_before_any_post() -> None:
    for field in ("effort", "reasoning_effort"):
        for bad in (None, "max", "off", "none", "disabled"):
            reg = registry()
            reg.data["models"]["kimi-code-main"]["settings"][field] = bad
            with pytest.raises(ConfigError):
                reg.resolve()
    handle = registry().resolve()[0]
    port = AnthropicMessages(
        base_url=handle.base_url,
        api_key="synthetic",
        model=handle.model,
        provider=handle.provider,
        caps=handle.caps,
        settings=handle.settings,
        transport=httpx.MockTransport(lambda _: pytest.fail("unverified protocol issued POST")),
    )
    with pytest.raises(ConfigError):
        port.complete([])
    assert port.request_count == 0

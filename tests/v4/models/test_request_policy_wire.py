"""K3 request policy exercises real wire adapters with synthetic HTTP only."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import CapabilityError
from mingjing_core.models.metering import request_meter
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage, ToolSpec
from mingjing_core.models.request_policy import sampling_body
from mingjing_core.models.transport import StreamingHTTP

from .test_protocols import recording

PROTOCOLS = [AnthropicMessages, OpenAICompat]
TOOL = ToolSpec("lookup", "查询合成日期", {"type": "object", "properties": {}})
CAPS = {
    "tools": True,
    "vision": True,
    "tool_choice": ["auto", "required", "none", "named"],
}


def wire_model(
    protocol: type[StreamingHTTP],
    *,
    model: str = "k3-256k",
    caps: dict[str, Any] | None = None,
    settings: dict[str, Any] | None = None,
) -> tuple[StreamingHTTP, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["User-Agent"] == "MingjingCore/3.0"
        data = (
            recording(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "text", "text": "合成回答"},
                },
                {"type": "content_block_stop", "index": 0},
                {"type": "message_stop"},
            )
            if protocol is AnthropicMessages
            else recording(
                {
                    "choices": [
                        {"delta": {"content": "合成回答"}, "finish_reason": "stop"}
                    ]
                }
            )
        )
        return httpx.Response(200, content=data)

    return (
        protocol(
            base_url="https://synthetic.invalid/v1",
            api_key="synthetic-test-only",
            model=model,
            provider="synthetic",
            caps={**CAPS, **(caps or {})},
            settings={"membership": True, **(settings or {})},
            transport=httpx.MockTransport(respond),
            sleep=lambda _: None,
        ),
        requests,
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("model_name", ["k3", "k3-256k", "kimi-k3"])
@pytest.mark.parametrize("tools", [None, [], [TOOL]])
@pytest.mark.parametrize("choice", ["none", "lookup", "named"])
def test_k3_rejects_unsafe_choice_before_meter_or_post(
    protocol: type[StreamingHTTP],
    model_name: str,
    tools: list[ToolSpec] | None,
    choice: str,
) -> None:
    model, requests = wire_model(protocol, model=model_name)
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(CapabilityError):
        model.complete([ChatMessage("user", "合成")], tools=tools, tool_choice=choice)
    assert requests == [] and metered == []
    assert model.request_count == model.quota_errors == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("choice", ["auto", "required"])
def test_single_k3_tool_preserves_safe_requested_choice(
    protocol: type[StreamingHTTP], choice: str
) -> None:
    model, requests = wire_model(protocol)
    assert (
        model.complete(
            [ChatMessage("user", "合成")], tools=[TOOL], tool_choice=choice
        ).text
        == "合成回答"
    )
    body = json.loads(requests[0].content)
    expected = (
        {"type": "any" if choice == "required" else "auto"}
        if protocol is AnthropicMessages
        else choice
    )
    assert body["tool_choice"] == expected
    assert len(body["tools"]) == model.request_count == len(requests) == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("choice", ["auto", "required"])
def test_multiple_k3_tools_keep_safe_requested_choice(
    protocol: type[StreamingHTTP], choice: str
) -> None:
    model, requests = wire_model(protocol)
    other = ToolSpec("calendar", "合成历法", {"type": "object", "properties": {}})
    model.complete([], tools=[TOOL, other], tool_choice=choice)
    expected = (
        {"type": "any" if choice == "required" else "auto"}
        if protocol is AnthropicMessages
        else choice
    )
    assert json.loads(requests[0].content)["tool_choice"] == expected


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("tools", [None, []])
def test_plain_k3_text_omits_tools_and_tool_choice(
    protocol: type[StreamingHTTP], tools: list[ToolSpec] | None
) -> None:
    model, requests = wire_model(protocol)
    model.complete([ChatMessage("user", "合成纯文字")], tools=tools)
    body = json.loads(requests[0].content)
    assert "tools" not in body and "tool_choice" not in body
    assert model.request_count == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("temperature", [None, 0.4])
def test_fixed_sampling_overrides_caller_and_settings(
    protocol: type[StreamingHTTP], temperature: float | None
) -> None:
    model, requests = wire_model(
        protocol,
        caps={"sampling_fixed": True},
        settings={"temperature": 0.7, "top_p": 0.2},
    )
    model.complete([], temperature=temperature)
    body = json.loads(requests[0].content)
    assert "temperature" not in body and "top_p" not in body


@pytest.mark.parametrize("fixed", [True, False])
def test_fixed_sampling_filters_both_fields_without_mutating_input(fixed: bool) -> None:
    original = {
        "model": "synthetic",
        "temperature": 0.4,
        "top_p": 0.2,
        "max_tokens": 20,
    }
    result = sampling_body(original, {"sampling_fixed": fixed})
    assert original["temperature"] == 0.4 and original["top_p"] == 0.2
    assert result == ({"model": "synthetic", "max_tokens": 20} if fixed else original)


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("choice", ["auto", "required", "none", "lookup"])
def test_non_k3_tool_choice_retains_portable_wire_contract(
    protocol: type[StreamingHTTP], choice: str
) -> None:
    model, requests = wire_model(protocol, model="portable-model")
    model.complete([], tools=[TOOL], tool_choice=choice)
    body = json.loads(requests[0].content)
    if protocol is AnthropicMessages:
        expected = (
            {"type": "tool", "name": "lookup"}
            if choice == "lookup"
            else {"type": "any" if choice == "required" else choice}
        )
    else:
        expected = (
            {"type": "function", "function": {"name": "lookup"}}
            if choice == "lookup"
            else choice
        )
    assert body["tool_choice"] == expected
    assert model.request_count == 1


@pytest.mark.parametrize("protocol", PROTOCOLS)
@pytest.mark.parametrize("choice", ["none", "lookup"])
def test_non_k3_no_tools_keeps_original_omission(
    protocol: type[StreamingHTTP], choice: str
) -> None:
    model, requests = wire_model(protocol, model="portable-model")
    model.complete([], tool_choice=choice)
    body = json.loads(requests[0].content)
    assert "tools" not in body and "tool_choice" not in body


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_nonfixed_sampling_keeps_explicit_temperature(
    protocol: type[StreamingHTTP],
) -> None:
    model, requests = wire_model(
        protocol, model="portable-model", settings={"temperature": 0.7}
    )
    model.complete([], temperature=0.4)
    assert json.loads(requests[0].content)["temperature"] == 0.4


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_explicit_required_still_requires_advertised_required_capability(
    protocol: type[StreamingHTTP],
) -> None:
    model, requests = wire_model(protocol, caps={"tool_choice": ["auto"]})
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(CapabilityError):
        model.complete([], tools=[TOOL], tool_choice="required")
    assert requests == [] and metered == [] and model.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_single_auto_needs_only_auto_capability(protocol: type[StreamingHTTP]) -> None:
    model, requests = wire_model(protocol, caps={"tool_choice": ["auto"]})
    model.complete([], tools=[TOOL], tool_choice="auto")
    expected = {"type": "auto"} if protocol is AnthropicMessages else "auto"
    assert json.loads(requests[0].content)["tool_choice"] == expected

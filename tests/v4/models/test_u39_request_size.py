"""The final serialized replay payload must pass size checks before metering."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import ModelPayloadTooLarge
from mingjing_core.models.metering import request_meter
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage, ToolCall, ToolSpec

from .test_u39_anthropic_wire import model_for
from .test_u39_policy_wire import data

PROTOCOLS = [AnthropicMessages, OpenAICompat]


@pytest.mark.parametrize("kind", ["signature", "redacted", "utf8", "escaped"])
def test_full_anthropic_private_replay_counts_before_meter_or_post(kind: str) -> None:
    port, requests = model_for()
    block: dict[str, Any] = {"type": "thinking", "thinking": "synthetic", "signature": "synthetic-signature"}
    if kind == "signature":
        block["signature"] = "x" * 1_900_000
    elif kind == "redacted":
        block = {"type": "redacted_thinking", "data": "x" * 1_900_000}
    elif kind == "utf8":
        block["thinking"] = "测" * 650_000
    else:
        block["signature"] = '"\\\n' * 400_000
    messages = [ChatMessage("assistant", tool_cycle="epoch", private_content=[block])]
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelPayloadTooLarge):
        port.complete(messages)
    assert requests == metered == [] and port.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_individually_small_reasoning_tools_and_results_still_count_as_one_full_body(protocol: type[Any]) -> None:
    port, requests = model_for(protocol, content=data(protocol))
    messages = [
        ChatMessage("user", "x" * 500_000),
        ChatMessage(
            "assistant",
            reasoning="x" * 500_000,
            reasoning_signature="s" * 500_000,
            tool_calls=[ToolCall("original-id", "lookup", {})],
            tool_cycle="epoch",
        ),
        ChatMessage("tool", "x" * 500_000, tool_call_id="original-id", tool_cycle="epoch"),
    ]
    tools = [ToolSpec("lookup", "synthetic", {"type": "object", "description": "x" * 500_000})]
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)), pytest.raises(ModelPayloadTooLarge):
        port.complete(messages, tools=tools)
    assert requests == metered == [] and port.request_count == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_replayed_reasoning_exact_serialized_boundary_is_enforced(protocol: type[Any]) -> None:
    port, requests = model_for(protocol, content=data(protocol))
    messages = [ChatMessage("assistant", reasoning="合成推理\n", reasoning_signature="opaque/+==", tool_cycle="epoch")]
    metered: list[int] = []
    with request_meter(lambda: metered.append(1)):
        port.complete(messages)
        wire = requests[0].content
        port.settings["max_request_bytes"] = len(wire)
        port.complete(messages)
        assert requests[1].content == wire
        port.settings["max_request_bytes"] = len(wire) - 1
        with pytest.raises(ModelPayloadTooLarge):
            port.complete(messages)
    assert len(requests) == len(metered) == port.request_count == 2

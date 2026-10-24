"""OpenAI reasoning field presence and real-user boundaries use captured JSON."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mingjing_core.models.errors import ModelProtocolError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.port import ChatMessage

from .test_protocols import recording
from .test_u39_anthropic_wire import model_for


def reply(reasoning: str) -> bytes:
    return recording(
        {"choices": [{"delta": {"reasoning_content": reasoning[:2]}}]},
        {
            "choices": [
                {
                    "delta": {
                        "reasoning_content": reasoning[2:],
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "opaque.provider/call:1",
                                "function": {"name": "lookup", "arguments": '{"day":"周六"}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
    )


@pytest.mark.parametrize("reasoning", ["", '完整推理\n含引号"与\\字符'])
def test_reasoning_presence_and_original_tool_identity_survive_same_epoch(reasoning: str) -> None:
    port, requests = model_for(
        OpenAICompat, content=reply(reasoning), caps={"reasoning_replay": False, "reasoning_field": None}
    )
    first = port.complete([ChatMessage("user", "合成问题")])
    assert first.reasoning == reasoning and first.reasoning_present
    port.complete(
        [
            ChatMessage("user", "合成问题"),
            first.as_chat(tool_cycle="epoch"),
            ChatMessage("tool", "合成结果", tool_call_id=first.tool_calls[0].id, tool_cycle="epoch"),
        ]
    )
    wire = json.loads(requests[1].content)["messages"][1]
    assert wire["reasoning_content"] == reasoning
    assert wire["tool_calls"][0]["id"] == "opaque.provider/call:1"
    assert json.loads(wire["tool_calls"][0]["function"]["arguments"]) == {"day": "周六"}


def test_reused_epoch_string_after_new_user_cannot_replay_old_reasoning() -> None:
    port, requests = model_for(OpenAICompat, content=reply("合成思考"))
    first = port.complete([])
    port.complete(
        [
            first.as_chat(tool_cycle="same"),
            ChatMessage("user", "新问题"),
            first.as_chat(tool_cycle="same"),
            ChatMessage("tool", "结果", tool_cycle="same", tool_call_id="id"),
        ]
    )
    wire = json.loads(requests[1].content)["messages"]
    assert "reasoning_content" not in wire[0]
    assert wire[2]["reasoning_content"] == "合成思考"


def test_non_k3_replay_capability_remains_authoritative() -> None:
    port, requests = model_for(OpenAICompat, model="portable", content=reply("合成"), caps={"reasoning_replay": False})
    first = port.complete([])
    port.complete([first.as_chat(tool_cycle="epoch")])
    assert "reasoning_content" not in json.loads(requests[1].content)["messages"][0]


@pytest.mark.parametrize("reasoning", [False, 1, [], {"private": "not-retained"}])
def test_invalid_reasoning_delta_fails_as_safe_protocol_error(reasoning: Any) -> None:
    port, requests = model_for(
        OpenAICompat,
        content=recording({"choices": [{"delta": {"reasoning_content": reasoning}, "finish_reason": "stop"}]}),
    )
    with pytest.raises(ModelProtocolError) as caught:
        port.complete([])
    assert len(requests) == 1 and "private" not in str(caught.value.safe_diagnostic())

"""Synthetic standard SSE shapes; none are claimed as recorded Kimi responses."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx
import pytest

from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import CapabilityError
from mingjing_core.models.port import ChatMessage

from .test_protocols import CAPS, TOOL, recording


def block_record(blocks: list[dict[str, Any]]) -> bytes:
    chunks: list[dict[str, Any]] = [{"type": "message_start", "message": {"usage": {"input_tokens": 5}}}]
    for index, block in enumerate(blocks):
        start = deepcopy(block)
        if start["type"] == "tool_use":
            start["input"] = {}
        chunks.append({"type": "content_block_start", "index": index, "content_block": start})
        if block["type"] == "tool_use":
            chunks.append(
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block["input"], ensure_ascii=False),
                    },
                }
            )
        chunks.append({"type": "content_block_stop", "index": index})
    chunks.extend([{"type": "message_delta", "delta": {"stop_reason": "end_turn"}}, {"type": "message_stop"}])
    return recording(*chunks)


def model_for(
    protocol: type[Any] = AnthropicMessages,
    *,
    content: bytes | None = None,
    model: str = "k3-256k",
    settings: dict[str, Any] | None = None,
    caps: dict[str, Any] | None = None,
) -> tuple[Any, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=content if content is not None else block_record([]))

    port = protocol(
        base_url="https://synthetic.invalid/v1",
        api_key="synthetic",
        model=model,
        provider="synthetic",
        caps={**CAPS, **(caps or {})},
        settings={"membership": True, **(settings or {})},
        transport=httpx.MockTransport(respond),
        max_retries=0,
        sleep=lambda _: None,
    )
    return port, requests


def interleaved() -> list[dict[str, Any]]:
    return [
        {"type": "thinking", "thinking": "第一段\n保持原话", "signature": "sig.A/+="},
        {"type": "tool_use", "id": "provider-original:call/A", "name": "lookup", "input": {"day": "周六"}},
        {"type": "thinking", "thinking": "", "signature": "sig.B/+="},
        {"type": "redacted_thinking", "data": "opaque.redacted/+="},
        {"type": "text", "text": "合成答复"},
    ]


def history(result: Any, cycle: str = "run:epoch-1") -> list[ChatMessage]:
    return [
        ChatMessage("user", "合成问题"),
        result.as_chat(tool_cycle=cycle),
        ChatMessage("tool", "合成结果", tool_call_id="provider-original:call/A", tool_cycle=cycle),
    ]


def test_full_interleaved_content_and_independent_signatures_roundtrip_exactly() -> None:
    blocks = interleaved()
    port, requests = model_for(content=block_record(blocks), caps={"reasoning_replay": False})
    first = port.complete([ChatMessage("user", "合成问题")], tools=[TOOL])
    assert first.private_content == blocks
    assert first.reasoning == "第一段\n保持原话" and first.reasoning_signature == "sig.A/+=sig.B/+="
    assert first.tool_calls[0].id == "provider-original:call/A" and first.reasoning_signature_missing == 0
    port.complete(history(first), tools=[TOOL])
    assert json.loads(requests[1].content)["messages"][1]["content"] == blocks
    assert len(requests) == port.request_count == 2


def test_start_values_and_delta_fragments_stay_in_their_original_block() -> None:
    data = recording(
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "thinking", "thinking": "start", "signature": "sig-start"},
        },
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "/tail"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "/one"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "/two"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": "start-text"}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "/tail"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_stop"},
    )
    port, requests = model_for(content=data)
    first = port.complete([ChatMessage("user", "合成问题")])
    assert first.reasoning == "start/tail" and first.text == "start-text/tail"
    assert first.private_content[0]["signature"] == "sig-start/one/two"
    port.complete([first.as_chat(tool_cycle="cycle")])
    assert json.loads(requests[1].content)["messages"][0]["content"] == first.private_content


@pytest.mark.parametrize("signature", [None, ""])
def test_kimi_missing_signature_is_counted_and_preserved_without_fabrication(signature: str | None) -> None:
    block = {"type": "thinking", "thinking": "合成缺签名推理"}
    if signature is not None:
        block["signature"] = signature
    port, requests = model_for(content=block_record([block]))
    first = port.complete([ChatMessage("user", "合成问题")])
    assert first.reasoning_signature_missing == port.reasoning_signature_missing == 1
    port.complete([first.as_chat(tool_cycle="cycle")])
    assert json.loads(requests[1].content)["messages"][0]["content"] == [block]


def test_non_k3_still_refuses_unsigned_thinking_replay_with_zero_new_post() -> None:
    port, requests = model_for(content=block_record([{"type": "thinking", "thinking": "合成"}]), model="portable")
    first = port.complete([])
    with pytest.raises(CapabilityError):
        port.complete([first.as_chat(tool_cycle="cycle")])
    assert len(requests) == port.request_count == 1


def test_new_real_user_removes_old_thinking_even_when_cycle_identifier_reused() -> None:
    port, requests = model_for(content=block_record(interleaved()))
    first = port.complete([])
    messages = history(first, "reused") + [ChatMessage("user", "新问题"), first.as_chat(tool_cycle="reused")]
    port.complete(messages)
    wire = json.loads(requests[1].content)["messages"]
    assert [block["type"] for block in wire[1]["content"]] == ["tool_use", "text"]
    assert wire[-1]["content"] == interleaved()


def test_untagged_canonical_content_cannot_replay_private_blocks() -> None:
    port, requests = model_for(content=block_record(interleaved()))
    first = port.complete([])
    port.complete([first.as_chat()])
    assert [block["type"] for block in json.loads(requests[1].content)["messages"][0]["content"]] == [
        "tool_use",
        "text",
    ]


def test_private_receipt_is_copied_and_hidden_from_repr() -> None:
    port, _ = model_for(content=block_record(interleaved()))
    result = port.complete([])
    chat = result.as_chat(tool_cycle="cycle")
    chat.private_content[0]["thinking"] = "separate-copy"
    assert result.private_content[0]["thinking"] == "第一段\n保持原话"
    assert all(secret not in repr(result) + repr(chat) for secret in ("sig.A", "opaque.redacted", "第一段"))
    events = list(port.stream([]))
    assert all(secret not in repr(events) for secret in ("sig.A", "opaque.redacted", "第一段"))


def test_stale_flat_text_cannot_silently_replace_canonical_wire() -> None:
    port, requests = model_for(content=block_record(interleaved()))
    result = port.complete([])
    result.text = "changed-flat-text"
    with pytest.raises(CapabilityError):
        port.complete([result.as_chat(tool_cycle="cycle")])
    assert len(requests) == port.request_count == 1

"""Malformed canonical responses cannot become a replayable assistant receipt."""

from __future__ import annotations

from typing import Any

import pytest

from mingjing_core.models.errors import CapabilityError, ModelProtocolError
from mingjing_core.models.port import ChatMessage, ToolCall

from .test_protocols import recording
from .test_u39_anthropic_wire import model_for

THINK = {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "合成"}}
STOP = {"type": "content_block_stop", "index": 0}
END = {"type": "message_stop"}


@pytest.mark.parametrize(
    "chunks",
    [
        [THINK, END],
        [THINK, THINK, STOP, END],
        [STOP, END],
        [THINK, STOP, STOP, END],
        [dict(THINK, index=True), STOP, END],
        [dict(THINK, index=-1), STOP, END],
        [dict(THINK, index=1), dict(STOP, index=1), END],
        [
            THINK,
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "wrong"}},
            STOP,
            END,
        ],
        [
            THINK,
            STOP,
            {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "late"}},
            END,
        ],
        [THINK, STOP, END, THINK],
        [dict(THINK, content_block={"type": "thinking", "thinking": "private", "signature": 1}), STOP, END],
        [dict(THINK, content_block={"type": "thinking", "thinking": 1}), STOP, END],
        [dict(THINK, content_block={"type": "redacted_thinking", "data": None}), STOP, END],
        [dict(THINK, content_block={"type": "future-unsupported", "secret": "not-retained"}), STOP, END],
    ],
)
def test_bad_block_shapes_fail_safely_without_replay(chunks: list[dict[str, Any]]) -> None:
    port, requests = model_for(content=recording(*chunks))
    with pytest.raises(ModelProtocolError) as caught:
        port.complete([])
    assert len(requests) == port.request_count == 1
    assert "private" not in str(caught.value) + str(caught.value.safe_diagnostic())
    assert caught.value.__cause__ is None


@pytest.mark.parametrize(
    "private",
    [
        {},
        [None],
        [{"type": "thinking", "thinking": 1}],
        [{"type": "text", "text": 1}],
        [{"type": "thinking", "thinking": "synthetic", "signature": False}],
        [{"type": "redacted_thinking", "data": False}],
    ],
)
def test_invalid_private_canonical_input_fails_before_post(private: Any) -> None:
    port, requests = model_for()
    with pytest.raises(CapabilityError):
        port.complete([ChatMessage("assistant", tool_cycle="epoch", private_content=private)])
    assert requests == [] and port.request_count == 0


def test_bool_numeric_tool_receipts_are_not_equal_for_canonical_replay() -> None:
    port, requests = model_for()
    message = ChatMessage(
        "assistant",
        tool_calls=[ToolCall("id", "lookup", {"value": True})],
        tool_cycle="epoch",
        private_content=[{"type": "tool_use", "id": "id", "name": "lookup", "input": {"value": 1}}],
    )
    with pytest.raises(CapabilityError):
        port.complete([message])
    assert requests == [] and port.request_count == 0


def test_legacy_unsigned_replay_reports_safe_outbound_count() -> None:
    port, requests = model_for()
    result = port.complete([ChatMessage("assistant", reasoning="synthetic", tool_cycle="epoch")])
    assert result.execution_meta["reasoning_replay_signature_missing"] == 1
    assert port.last_execution_meta["reasoning_replay_signature_missing"] == 1
    assert len(requests) == 1 and "synthetic" not in str(result.execution_meta)

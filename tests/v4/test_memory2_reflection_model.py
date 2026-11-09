"""ModelReflection against a fake port: background lane, one forced tool call, strict parsing."""

from __future__ import annotations

import pytest

from mingjing_core.application import memory2_reflection_model as module
from mingjing_core.application.memory2_reflection_model import ModelReflection, load_prompt, parse_items
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.port import AssistantMessage, ModelPort, ToolCall
from mingjing_core.models.quota_runtime import current_scope

PAYLOAD = {
    "messages": [{"id": "msg_a", "content": "我喜欢合成徒步"}, {"id": "msg_b", "needs_ask": True}],
    "profile": [],
}
GOOD = {"message_id": "msg_a", "quote": "我喜欢合成徒步", "kind": "preference", "explicit": True, "summary": "喜欢徒步"}


class FakePort(ModelPort):
    def __init__(self, calls):
        self.calls, self.seen = calls, []

    def complete(self, messages, **kwargs):
        self.seen.append((messages, kwargs, current_scope().lane))
        return AssistantMessage(tool_calls=list(self.calls))


def test_one_forced_background_call_returns_checked_items():
    port = FakePort([ToolCall(id="t1", name="submit_memories", arguments={"items": [GOOD]})])
    assert ModelReflection(port).extract(PAYLOAD) == [GOOD]
    messages, kwargs, lane = port.seen[0]
    assert lane == "background" and kwargs["tool_choice"] == "required" and kwargs["temperature"] == 0
    assert messages[0].role == "system" and "submit_memories" in messages[0].content
    assert "needs_ask" in messages[1].content and "合成徒步" in messages[1].content


@pytest.mark.parametrize(
    "calls",
    [
        [],
        [ToolCall(id="t1", name="other", arguments={"items": []})],
        [ToolCall(id="t1", name="submit_memories", arguments={"items": []})] * 2,
        [ToolCall(id="t1", name="submit_memories", arguments={"items": [dict(GOOD, message_id="msg_b")]})],
        [ToolCall(id="t1", name="submit_memories", arguments={"items": [dict(GOOD, kind="profile")]})],
        [ToolCall(id="t1", name="submit_memories", arguments={"items": [dict(GOOD, explicit="yes")]})],
        [ToolCall(id="t1", name="submit_memories", arguments={"items": [dict(GOOD, extra=1)]})],
    ],
)
def test_malformed_or_out_of_scope_output_is_rejected(calls):
    with pytest.raises(EvidenceError):
        ModelReflection(FakePort(calls)).extract(PAYLOAD)


def test_item_limit_and_prompt_pin(monkeypatch):
    with pytest.raises(EvidenceError):
        parse_items({"items": [GOOD] * 21}, {"msg_a"})
    assert load_prompt().startswith("你在整理")
    monkeypatch.setattr(module, "PROMPT_SHA256", "0" * 64)
    with pytest.raises(EvidenceError):
        load_prompt()

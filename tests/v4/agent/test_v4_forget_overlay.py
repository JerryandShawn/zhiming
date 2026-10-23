"""Query migration obtains an ID only from a uniquely linked real tool message."""

import json

import pytest

from mingjing_core.models.errors import ModelProtocolError
from mingjing_core.models.port import ChatMessage, ToolCall
from tools.eval.targets.v4_scripted import unique_memory_fact


def response(items, *, call_name="memory_search"):
    call = ToolCall("search-call", call_name, {"query": "焦虑症"})
    return [
        ChatMessage("assistant", tool_calls=[call]),
        ChatMessage("tool", json.dumps({"ok": True, "data": {"items": items}}), tool_call_id=call.id),
    ]


def test_unique_fact_id_is_read_from_the_matching_search_tool_response():
    assert unique_memory_fact(response([{"entity_kind": "fact", "id": "actual-pg-fact"}])) == "actual-pg-fact"


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"entity_kind": "note", "id": "x"}],
        [{"entity_kind": "fact", "id": "a"}, {"entity_kind": "fact", "id": "b"}],
    ],
)
def test_missing_nonfact_and_multiple_real_search_results_cannot_choose_an_id(items):
    with pytest.raises(ModelProtocolError):
        unique_memory_fact(response(items))


def test_nonsearch_or_model_text_cannot_supply_a_search_result():
    items = [{"entity_kind": "fact", "id": "forged"}]
    with pytest.raises(ModelProtocolError):
        unique_memory_fact(response(items, call_name="memory_write"))
    with pytest.raises(ModelProtocolError):
        unique_memory_fact([ChatMessage("assistant", json.dumps({"data": {"items": items}}))])

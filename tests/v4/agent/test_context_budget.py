"""The budget counts full requests and labels its offline limitations honestly."""

from __future__ import annotations

import copy
import json
from dataclasses import replace

import pytest

from mingjing_core.agent.context_budget import apply_budget, assert_live_allowed, count_request
from mingjing_core.agent.context_types import (
    BudgetPolicy,
    ContextInputError,
    ContextItem,
    ContextLayer,
    InputMeterUnverified,
    RequiredContextOverflow,
)
from mingjing_core.models.port import ChatMessage, Part, ToolCall, ToolSpec


def layers(text: str) -> tuple[ContextLayer, ...]:
    return (ContextLayer("L6", (ContextItem("current", (ChatMessage("user", text),), True),)),)


def request_of_size(size: int) -> tuple[ContextLayer, ...]:
    overhead = count_request((ChatMessage("user", ""),)).policy_units
    return layers("x" * (size - overhead))


def cycle(content: str, *, summary: str | None = None) -> tuple[ContextLayer, ...]:
    assistant = ChatMessage(
        "assistant",
        "正在读取",
        [ToolCall("call-1", "search", {"query": "考研"})],
        reasoning="private reasoning",
        reasoning_signature="signature",
        tool_cycle="run:e0",
    )
    result = ChatMessage("tool", content, tool_call_id="call-1", tool_cycle="run:e0")
    return (ContextLayer("CYCLE", (ContextItem("a", (assistant,), True), ContextItem("t", (result,), True, summary))),)


@pytest.mark.parametrize("size", [119_999, 120_000, 120_001, 179_999, 180_000])
def test_exact_policy_boundaries_do_not_claim_provider_tokens(size: int) -> None:
    result = apply_budget(request_of_size(size))
    assert result.meter.policy_units == size
    assert result.meter.unit == "policy_units"
    assert result.meter.actual_input_tokens is result.meter.input_token_upper_bound is None
    with pytest.raises(InputMeterUnverified):
        assert_live_allowed(result)


def test_required_above_hard_max_is_rejected_without_truncation() -> None:
    value = request_of_size(180_001)
    before = copy.deepcopy(value)
    with pytest.raises(RequiredContextOverflow):
        apply_budget(value)
    assert value == before


@pytest.mark.parametrize("text", ["中文", "ASCII", "🙂", "e\u0301", "<|open|>", '转义"\\'])
def test_unicode_and_control_looking_text_are_counted_without_rewriting(text: str) -> None:
    result = apply_budget(layers(text))
    assert result.messages[0].content == text
    assert result.meter.policy_units == result.meter.serialized_bytes


@pytest.mark.parametrize("field", ["reasoning", "reasoning_signature", "tool_cycle"])
def test_nonvisible_assistant_fields_change_the_complete_request_meter(field: str) -> None:
    original = ChatMessage("assistant", "正文")
    changed = replace(original, **{field: "private" * 100})
    assert count_request((changed,)).policy_units > count_request((original,)).policy_units


def test_tools_schema_and_arguments_are_measured() -> None:
    small = ToolSpec("search", "查找", {"type": "object"})
    large = replace(small, description="说明" * 1000, parameters={"type": "object", "description": "x" * 1000})
    assert count_request((), (large,)).policy_units > count_request((), (small,)).policy_units + 3000
    first = cycle('{"ok":true}')
    original = first[0].items[0].messages[0]
    modified = replace(original, tool_calls=[ToolCall("call-1", "search", {"query": "x" * 2000})])
    assert count_request((modified, first[0].items[1].messages[0])).policy_units > 2000


def test_old_history_then_low_rank_retrieval_are_removed_in_order() -> None:
    required = layers("现在的问题")
    value = (
        ContextLayer("L5", (ContextItem("old", (ChatMessage("user", "h" * 121_000),)),)),
        ContextLayer("L4", (ContextItem("hit", (ChatMessage("system", "r" * 40_000),)),)),
        *required,
    )
    result = apply_budget(value)
    assert [item["action"] for item in result.compression_trace] == ["L5_drop", "L4_drop"]
    assert result.compression_trace[0]["before"] > 120_000
    assert result.messages == required[0].items[0].messages


def test_tool_summary_keeps_receipt_alias_pair_and_full_reasoning() -> None:
    content = json.dumps({"ok": True, "data": "x" * 160_000, "receipt": {"write_status": "saved"}, "alias": "f1"})
    value = cycle(content, summary="已保存一项")
    before = copy.deepcopy(value)
    result = apply_budget(value)
    assert result.compression_trace[0]["action"] == "tool_summary"
    tool = result.messages[-1]
    assert tool.tool_call_id == "call-1"
    assert json.loads(tool.content)["receipt"] == {"write_status": "saved"}
    assert json.loads(tool.content)["alias"] == "f1"
    assert result.messages[0].reasoning == "private reasoning"
    assert result.messages[0].reasoning_signature == "signature"
    assert before == value


@pytest.mark.parametrize(
    "content", ["not-json" * 30_000, json.dumps({"data": "x" * 180_000})], ids=["non-json", "no-summary"]
)
def test_large_tool_without_a_safe_summary_is_not_silently_truncated(content: str) -> None:
    with pytest.raises(RequiredContextOverflow):
        apply_budget(cycle(content))


@pytest.mark.parametrize("choice", ["none", "named", "search"])
def test_unsupported_tool_choice_is_rejected_before_any_transport(choice: str) -> None:
    with pytest.raises(ContextInputError):
        apply_budget(layers("当前问题"), tool_choice=choice)


@pytest.mark.parametrize("content", ["\ud800", float("nan"), [Part(type="image", data="private")]])
def test_unsupported_or_invalid_content_is_rejected_safely(content: object) -> None:
    with pytest.raises(ContextInputError) as error:
        apply_budget((ContextLayer("L6", (ContextItem("bad", (ChatMessage("user", content),), True),)),))
    assert "private" not in str(error.value)


@pytest.mark.parametrize("role,call_id", [("tool", "absent"), ("assistant", None)])
def test_orphan_or_unfinished_tool_cycle_is_rejected(role: str, call_id: str | None) -> None:
    message = ChatMessage(role, "", tool_call_id=call_id)
    if role == "assistant":
        message = replace(message, tool_calls=[ToolCall("open", "search", {})])
    with pytest.raises(ContextInputError):
        count_request((message,))


@pytest.mark.parametrize(
    "kwargs", [{"target": 0}, {"hard_max": 100}, {"history_limit": 1001}, {"target": True}, {"fact_limit": 10001}]
)
def test_invalid_policy_cannot_disable_the_hard_gate(kwargs: dict[str, int]) -> None:
    with pytest.raises(ContextInputError):
        BudgetPolicy(**kwargs)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), object()], ids=["nan", "infinity", "object"])
def test_non_json_or_nonfinite_tool_schemas_are_rejected(value: object) -> None:
    with pytest.raises(ContextInputError):
        count_request((), (ToolSpec("search", "查找", {"value": value}),))


def test_required_without_a_tool_is_rejected() -> None:
    with pytest.raises(ContextInputError):
        count_request((), tool_choice="required")


def test_tool_summary_preserves_plural_receipts_and_stable_mutation_metadata() -> None:
    metadata = {
        "receipts": [{"fact_id": "f1", "revision": 2}],
        "operation_id": "run:r:e0:s2",
        "status": "saved",
        "write_status": "saved",
    }
    content = json.dumps(dict(metadata, data="x" * 160_000))
    result = apply_budget(cycle(content, summary="已保存两条合成资料"))
    summarized = json.loads(result.messages[-1].content)
    assert all(summarized[key] == value for key, value in metadata.items())


@pytest.mark.parametrize("unsafe", [{"commit_token": "unknown"}, {"data": {"status": "saved"}}])
def test_unknown_tool_envelopes_are_not_summarized(unsafe: dict[str, object]) -> None:
    if isinstance(unsafe.get("data"), dict):
        value = {"data": dict(unsafe["data"], payload="x" * 181_000)}
    else:
        value = dict({"data": "x" * 181_000}, **unsafe)
    content = json.dumps(value)
    with pytest.raises(RequiredContextOverflow):
        apply_budget(cycle(content, summary="不能证明安全的摘要"))


@pytest.mark.parametrize("tag", [None, "", "run:e1"])
def test_tool_result_must_share_the_nonempty_assistant_epoch_tag(tag: str | None) -> None:
    messages = cycle('{"ok":true}')[0].items
    with pytest.raises(ContextInputError):
        count_request((messages[0].messages[0], replace(messages[1].messages[0], tool_cycle=tag)))


def test_untagged_tool_cycles_are_rejected_but_old_plain_history_is_legal() -> None:
    messages = cycle('{"ok":true}')[0].items
    with pytest.raises(ContextInputError):
        count_request(tuple(replace(item.messages[0], tool_cycle=None) for item in messages))
    assert count_request((ChatMessage("user", "旧问题"), ChatMessage("assistant", "旧回答"))).policy_units > 0

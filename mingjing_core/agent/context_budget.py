"""Bound complete offline requests without inventing a provider token count."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace

from mingjing_core.models.port import ChatMessage, ToolSpec

from .context_types import (
    BudgetPolicy,
    BudgetResult,
    ContextInputError,
    ContextLayer,
    InputMeterUnverified,
    MeterResult,
    RequiredContextOverflow,
)


def _validate_messages(messages: tuple[ChatMessage, ...]) -> None:
    pending: set[str] = set()
    seen: set[str] = set()
    cycle_tag: str | None = None
    for message in messages:
        if message.role not in {"system", "user", "assistant", "tool"}:
            raise ContextInputError()
        if not isinstance(message.content, str):
            raise ContextInputError("context_text_only")
        if not all(isinstance(value, str) for value in (message.reasoning, message.reasoning_signature)):
            raise ContextInputError()
        if message.role == "user":
            cycle_tag = None
        if message.tool_cycle is not None:
            if not isinstance(message.tool_cycle, str) or not message.tool_cycle.strip():
                raise ContextInputError("context_cycle_invalid")
            if cycle_tag is not None and message.tool_cycle != cycle_tag:
                raise ContextInputError("context_cycle_invalid")
            cycle_tag = message.tool_cycle
        if message.tool_calls and not cycle_tag:
            raise ContextInputError("context_cycle_invalid")
        if message.role in {"assistant", "tool"} and cycle_tag is not None and message.tool_cycle != cycle_tag:
            raise ContextInputError("context_cycle_invalid")
        if message.role == "tool":
            if message.tool_call_id not in pending:
                raise ContextInputError("context_tool_pair_invalid")
            pending.remove(message.tool_call_id)
        elif pending:
            raise ContextInputError("context_tool_pair_invalid")
        if message.tool_calls and message.role != "assistant":
            raise ContextInputError("context_tool_pair_invalid")
        for call in message.tool_calls:
            if not call.id or call.id in seen or not call.name or not isinstance(call.arguments, dict):
                raise ContextInputError("context_tool_pair_invalid")
            pending.add(call.id)
            seen.add(call.id)
    if pending:
        raise ContextInputError("context_tool_pair_invalid")


def count_request(
    messages: tuple[ChatMessage, ...],
    tools: tuple[ToolSpec, ...] = (),
    *,
    tool_choice: str = "auto",
) -> MeterResult:
    """Count every normalized field as policy units, including private reasoning."""
    if tool_choice not in {"auto", "required"} or tool_choice == "required" and not tools:
        raise ContextInputError("context_tool_choice_invalid")
    _validate_messages(messages)
    if any(not tool.name or not isinstance(tool.parameters, dict) for tool in tools):
        raise ContextInputError("context_tools_invalid")
    if len({tool.name for tool in tools}) != len(tools) or len(tools) > 15:
        raise ContextInputError("context_tools_invalid")
    try:
        body = {
            "messages": [asdict(message) for message in messages],
            "tools": [asdict(tool) for tool in tools],
            "tool_choice": tool_choice,
        }
        encoded = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        size = len(encoded.encode("utf-8", errors="strict"))
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
        raise ContextInputError("context_serialization_invalid") from None
    return MeterResult(policy_units=size, serialized_bytes=size)


def _flatten(layers: tuple[ContextLayer, ...]) -> tuple[ChatMessage, ...]:
    return tuple(message for layer in layers for item in layer.items for message in item.messages)


def _remove_candidate(
    layers: tuple[ContextLayer, ...],
) -> tuple[tuple[ContextLayer, ...], str] | None:
    for name, reverse in (("L5", False), ("L4", True)):
        for index, layer in enumerate(layers):
            if layer.name != name:
                continue
            positions = range(len(layer.items) - 1, -1, -1) if reverse else range(len(layer.items))
            for position in positions:
                if not layer.items[position].required:
                    items = layer.items[:position] + layer.items[position + 1 :]
                    changed = replace(layer, items=items)
                    return layers[:index] + (changed,) + layers[index + 1 :], name + "_drop"
    return None


def _summary_content(message: ChatMessage, summary: str) -> str | None:
    try:
        value = json.loads(message.content)
    except (ValueError, TypeError):
        return None
    if not isinstance(value, dict):
        return None
    preserved_keys = (
        "ok",
        "receipt",
        "receipts",
        "alias",
        "aliases",
        "ends_turn",
        "operation_id",
        "status",
        "write_status",
    )
    if set(value) - {*preserved_keys, "data", "summary"}:
        return None
    if value.get("data") is not None and not isinstance(value["data"], str):
        return None
    preserved = {key: value[key] for key in preserved_keys if key in value}
    try:
        return json.dumps(
            dict(preserved, summary=summary),
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (ValueError, TypeError):
        return None


def _summarize_candidate(
    layers: tuple[ContextLayer, ...], policy: BudgetPolicy
) -> tuple[tuple[ContextLayer, ...], str] | None:
    for index, layer in enumerate(layers):
        if layer.name != "CYCLE":
            continue
        for position, item in enumerate(layer.items):
            if not item.summary or len(item.messages) != 1:
                continue
            message = item.messages[0]
            if message.role != "tool" or len(message.content.encode("utf-8")) <= policy.large_tool:
                continue
            content = _summary_content(message, item.summary)
            if content is None or len(content.encode("utf-8")) >= len(message.content.encode("utf-8")):
                continue
            changed = replace(item, messages=(replace(message, content=content),), summary=None)
            items = layer.items[:position] + (changed,) + layer.items[position + 1 :]
            return layers[:index] + (replace(layer, items=items),) + layers[index + 1 :], "tool_summary"
    return None


def apply_budget(
    layers: tuple[ContextLayer, ...],
    tools: tuple[ToolSpec, ...] = (),
    *,
    policy: BudgetPolicy | None = None,
    tool_choice: str = "auto",
) -> BudgetResult:
    """Compress optional evidence; never truncate required instructions or reasoning."""
    policy = policy or BudgetPolicy()
    layers, tools = copy.deepcopy(layers), copy.deepcopy(tools)
    trace: list[dict[str, str | int]] = []
    meter = count_request(_flatten(layers), tools, tool_choice=tool_choice)
    maximum_steps = sum(len(layer.items) for layer in layers)
    for _ in range(maximum_steps):
        if meter.policy_units <= policy.target:
            break
        candidate = _remove_candidate(layers) or _summarize_candidate(layers, policy)
        if candidate is None:
            break
        changed, action = candidate
        measured = count_request(_flatten(changed), tools, tool_choice=tool_choice)
        if measured.policy_units >= meter.policy_units:
            raise ContextInputError("context_compression_not_reducing")
        trace.append(
            {
                "action": action,
                "before": meter.policy_units,
                "after": measured.policy_units,
            }
        )
        layers, meter = changed, measured
    if meter.policy_units > policy.hard_max:
        raise RequiredContextOverflow()
    return BudgetResult(layers, _flatten(layers), tools, meter, tuple(trace))


def assert_live_allowed(result: BudgetResult) -> None:
    """Fail closed unless an application-injected provider meter covers this request."""
    meter = result.meter
    if not meter.live_admissible or meter.input_token_upper_bound is None or not meter.token_meter_version:
        raise InputMeterUnverified()
    if meter.input_token_upper_bound > 180_000:
        raise RequiredContextOverflow()

"""Offline schemas, visibility and trusted execution identity contracts."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.agent.tool_visibility import RESIDENT_TOOLS, VisibilityState
from mingjing_core.agent.toolkit import DEFINITIONS, ToolContext, ToolDefinition, ToolRegistry, ToolResult
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.domain.contracts import EvidenceError


class SchemaOnlyService(AgentToolsService):
    """Only schema tests replace the PG visibility boundary; PG tests prove identity."""

    def __init__(self) -> None:
        super().__init__(None)

    def tarot_visibility(self, ctx: ToolContext) -> str:
        return "tarot_start"

    def visibility_state(self, ctx: ToolContext) -> VisibilityState:
        return VisibilityState(tarot_topic=True, case_bound=True)

    def chart_available(self, ctx: ToolContext) -> bool:
        return not ctx.private and not ctx.crisis


def context(**changes: Any) -> ToolContext:
    return replace(
        ToolContext("alice", "run", "self", 0, 1, "private-token", "time_context", "a" * 64, "life:self"), **changes
    )


def test_registry_order_visibility_and_flattened_schemas() -> None:
    registry = ToolRegistry(SchemaOnlyService())
    specs = registry.specs(context())
    assert [item.name for item in specs] == [
        *RESIDENT_TOOLS,
        "tarot_start",
        "case_list",
        "case_update",
        "case_add_event",
    ]
    assert len(DEFINITIONS) == 25 and len(specs) == 14
    for item in specs:
        text = str(item.parameters)
        assert "$ref" not in text and "$defs" not in text and "anyOf" not in text
        assert item.parameters["additionalProperties"] is False
        assert "返回" in item.description and ("副作用" in item.description or "会" in item.description)
    assert [item.name for item in registry.specs(context(crisis=True))] == ["time_context", "memory_search"]
    assert all(
        registry.read_only(item.name) or item.name in {"ask_user", "set_reminder"}
        for item in registry.specs(context(incognito=True))
    )
    assert not registry.read_only("ask_user")
    private_names = {item.name for item in registry.specs(context(thread_id="incognito:one"))}
    assert len(private_names) == 6 and "set_reminder" not in private_names and "date_calc" not in private_names
    assert not private_names.intersection({"memory_write", "note_write", "memory_forget", "schedule_followup"})


def test_registry_refuses_extra_authority_parameters_and_hidden_tools() -> None:
    registry = ToolRegistry(SchemaOnlyService())
    result = registry.execute("time_context", {"owner": "bob"}, context())
    assert not result.ok and result.data["code"] == "invalid_arguments"
    result = registry.execute("memory_write", {}, context(crisis=True))
    assert not result.ok and result.data["code"] == "tool_unavailable"
    with pytest.raises(ValueError):
        ToolRegistry(AgentToolsService(None), definitions=DEFINITIONS + DEFINITIONS)


def test_unreviewed_extra_tool_is_not_disclosed() -> None:
    extra = ToolDefinition("extra_time", DEFINITIONS[0].parameters, DEFINITIONS[0].description)
    registry = ToolRegistry(SchemaOnlyService(), definitions=DEFINITIONS + (extra,))
    specs = registry.specs(context())
    assert len(specs) == 14 and "extra_time" not in {tool.name for tool in specs}


@pytest.mark.parametrize("changes", [{"epoch": True}, {"seq": 0}, {"input_fp": "raw"}, {"thread_id": ""}])
def test_invalid_context_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(EvidenceError):
        context(**changes)


def test_result_and_context_repr_do_not_expose_private_bodies() -> None:
    result = ToolResult(ok=True, data={"quote": "合成私人正文"}, receipt={"id": "item"}, summary="已保存")
    assert "合成私人正文" not in repr(result)
    assert "private-token" not in repr(context())
    assert context().operation_id == "run:run:e0:s1"

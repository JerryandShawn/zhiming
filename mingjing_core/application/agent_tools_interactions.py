"""Registered case, clarification and scheduling service dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_cases import execute_case
from mingjing_core.application.agent_tools_clarification import execute_clarification
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.agent_tools_followups import execute_schedule
from mingjing_core.domain.contracts import EvidenceError

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

INTERACTION_NAMES = frozenset(
    {
        "case_list",
        "case_update",
        "case_add_event",
        "ask_user",
        "present_options",
        "schedule_followup",
        "set_reminder",
    }
)


def execute_interaction(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    if name.startswith("case_"):
        return execute_case(service, name, args, ctx)
    if name in {"ask_user", "present_options"}:
        return execute_clarification(service, name, args, ctx)
    if name in {"schedule_followup", "set_reminder"}:
        return execute_schedule(service, name, args, ctx)
    raise EvidenceError("未注册的交互工具")

"""Audited read-only handlers release owner locks during pure computation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.domain.contracts import EvidenceError, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

PURE_READS = frozenset({"time_context", "calendar_lookup", "memory_search", "profile_get", "case_list", "date_calc"})


def execute_pure_read(service: AgentToolsService, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if (
        name not in PURE_READS
        or name != ctx.name
        or tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp
    ):
        raise EvidenceError("只读调用与受信步骤不符")
    if ctx.crisis and name not in {"time_context", "memory_search"}:
        raise ScopeError("危机模式下此读取不可用")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
    result = calculate_read(service, name, args, ctx)
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if result.receipt is not None or result.ends_turn:
            raise EvidenceError("纯读取不能产生写入回执或结束本轮")
    return result


def calculate_read(service: AgentToolsService, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    from mingjing_core.application.agent_tools_cases import execute_case
    from mingjing_core.application.agent_tools_computation import date_calc
    from mingjing_core.application.agent_tools_reads import execute_read

    # case_list retains its own short index authorization; no mutation branch is admitted.
    if name == "case_list":
        return execute_case(service, name, args, ctx)
    if name == "date_calc":
        return date_calc(args, ref_time=ctx.at or service.clock.now(), timezone=service.timezone(ctx))
    return execute_read(service, name, args, ctx)

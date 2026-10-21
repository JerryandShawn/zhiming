"""A body-free persistent refusal is checked in the actual effect transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.privacy_run_barrier import run_persistence_blocked
from mingjing_core.domain.contracts import EvidenceError

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService


def privacy_refusal(
    service: AgentToolsService, name: str, arguments: dict[str, Any], ctx: ToolContext
) -> ToolResult | None:
    if getattr(service.repo._local, "connection", None) is None:
        raise EvidenceError("隐私闸门需要实际副作用事务")
    if not run_persistence_blocked(service.repo, service.repo.fetch_run(ctx.owner, ctx.run_id)):
        return None
    receipt = service.repo.mutation_request(
        ctx.owner,
        "agent_" + name,
        ctx.operation_id,
        arguments,
        lambda: {"write_status": "stopped", "code": "privacy_optout"},
    )
    return ToolResult(
        ok=receipt.get("write_status") == "saved",
        receipt=receipt,
        summary="本次保存状态已核对；本轮后续保存已停止",
    )

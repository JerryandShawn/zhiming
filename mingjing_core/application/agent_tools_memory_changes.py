"""Actual source-driven update discovery inside the existing writer transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.application.agent_tools_projection import sources_active
from mingjing_core.application.memory2_explicit_changes import MemoryExplicitChangeService
from mingjing_core.memory.change_signals import explicit_replacement_slot
from mingjing_core.memory.slots import normalize_slot

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext


def explicit_candidates(service: AgentToolsService, args: dict, ctx: ToolContext) -> list[dict]:
    rows = service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
    return [
        row
        for row in rows
        if row.get("case_id") == args.get("case_id")
        and not row.get("field")
        and not row.get("valid_to")
        and explicit_replacement_slot(row.get("content", ""), args["quote"])
        and normalize_slot(row.get("slot")) in {None, explicit_replacement_slot(row["content"], args["quote"])}
        and sources_active(service, row, ctx)
    ]


def apply_explicit_change(service: AgentToolsService, args: dict, ctx: ToolContext, row: dict) -> dict | None:
    candidates = [old for old in explicit_candidates(service, args, ctx) if old["id"] != row["id"]]
    if len(candidates) != 1:
        return None
    old = candidates[0]
    return MemoryExplicitChangeService(service.memory).update(
        ctx.owner,
        ctx.subject,
        old["id"],
        row["id"],
        expected_old_revision=old["revision"],
        expected_new_revision=row["revision"],
        operation_id=ctx.operation_id + ":explicit-change",
    )


def verify_updated(service: AgentToolsService, ctx: ToolContext, receipt: dict) -> None:
    change = service.repo.get(ctx.owner, "proposal", receipt["ids"][0])
    old_id, new_id = change["fact_ids"]
    MemoryExplicitChangeService(service.memory).slots._verify_receipt(ctx.owner, ctx.subject, old_id, new_id, receipt)

"""Conservative fact deduplication inside the existing v4 writer transaction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_projection import sources_active
from mingjing_core.memory2.dedup import normalized
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext


def same_fact(left: dict[str, Any], right: dict[str, Any]) -> bool:
    fields = ("subject_id", "case_id", "kind", "requested_kind", "field", "value", "event_at", "event_end", "slot")
    return (
        all(left.get(field) == right.get(field) for field in fields)
        and not left.get("valid_to")
        and not right.get("valid_to")
        and normalized(left.get("content", "")) == normalized(right.get("content", ""))
        and left.get("assertion_status") == right.get("assertion_status")
    )


def merge_written_fact(
    service: AgentToolsService, ctx: ToolContext, incoming: dict[str, Any]
) -> tuple[dict[str, Any], str | None]:
    """Only a fact already admitted by the original-source writer may reach here."""
    candidates = service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
    for old in candidates:
        if old["id"] == incoming["id"] or not same_fact(old, incoming):
            continue
        if not sources_active(service, old, ctx) or not sources_active(service, incoming, ctx):
            continue
        if old.get("valid_from", "") > incoming.get("valid_from", ""):
            continue
        return _merge(service, ctx, old, incoming)
    return incoming, None


def _merge(
    service: AgentToolsService, ctx: ToolContext, old: dict[str, Any], incoming: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    refs = list(old["source_refs"])
    refs.extend(ref for ref in incoming["source_refs"] if ref not in refs)
    merged = service.repo.update(
        ctx.owner,
        "fact",
        old["id"],
        {"source_refs": refs},
        expected_revision=old["revision"],
        operation_id=ctx.operation_id + ":merge",
    )
    retired = service.repo.update(
        ctx.owner,
        "fact",
        incoming["id"],
        {"status": "merged", "merged_into": old["id"]},
        expected_revision=incoming["revision"],
        operation_id=ctx.operation_id + ":merged-input",
    )
    ident = "memory2_change_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    # A non-pending P3 proposal record reuses existing privacy-cascade handling.
    # It cannot appear as a user fact or as a second confirmation workflow.
    service.repo.put(
        ctx.owner,
        "proposal",
        ident,
        {
            "kind": "memory2_merge_undo",
            "status": "applied",
            "target_fact_id": old["id"],
            "target_revision": merged["revision"],
            "incoming_fact_id": incoming["id"],
            "incoming_revision": retired["revision"],
            "before": old,
            "source_refs": refs,
            "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
            "fact_ids": [old["id"], incoming["id"]],
        },
        subject=ctx.subject,
        case_id=old.get("case_id"),
        expected_revision=0,
        operation_id=ctx.operation_id + ":merge-undo-record",
    )
    return merged, ident

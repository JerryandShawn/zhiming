"""Admit initial model-declared slots; replacement stays closed until its commit proof is integrated."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_policy import KIND_MAP
from mingjing_core.application.memory2_merge import same_fact
from mingjing_core.memory.slots import SLOTS, compatible_statement, normalize_slot

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext


def prepare_slot_write(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    slot = normalize_slot(args.get("slot"))
    if slot is None:
        return metadata, None
    if not compatible_statement(slot, args["quote"]):
        return metadata, {"write_status": "rejected", "code": "slot_statement_mismatch"}
    prepared = dict(metadata, slot=slot)
    if SLOTS[slot].cardinality == "multi":
        return prepared, None
    peers = [
        row
        for row in service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
        if (row.get("slot") == slot or (not row.get("slot") and compatible_statement(slot, row.get("content", ""))))
        and row.get("case_id") == args.get("case_id")
        and not row.get("valid_to")
    ]
    # Unslotted compatible rows are ambiguity guards only; never assign them a
    # slot or infer a replacement target from a lexical clue.
    if not peers:
        return prepared, None
    prospective = dict(
        prepared,
        subject_id=ctx.subject,
        case_id=args.get("case_id"),
        kind=KIND_MAP.get(args["kind"], args["kind"]),
        requested_kind=args["kind"],
        content=args["quote"],
        assertion_status="user_asserted",
    )
    if len(peers) == 1 and same_fact(peers[0], prospective):
        return prepared, None
    # Persisting a second current value or returning saved for an update would
    # bypass the mainline's still-missing strict updated receipt proof.
    return metadata, {"write_status": "needs_confirmation", "code": "slot_update_requires_commit_proof"}

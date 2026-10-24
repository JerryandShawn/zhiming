"""Conflict candidates reuse P3 proposals and never silently overwrite existing facts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_policy import (
    KIND_MAP,
    sensitivity_categories,
)
from mingjing_core.application.agent_tools_projection import sources_active
from mingjing_core.application.memory2_fact_authority import authorized_fact, statement_instant
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory2.conflict_candidates import opposing_preferences
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext
    from mingjing_core.application.memory import MemoryService


def conflict_candidate(service: AgentToolsService, args: dict, ctx: ToolContext) -> dict | None:
    if args["kind"] not in {"preference", "habit"}:
        return None
    boundary = history_instant(service.memory.get_source(ctx.owner, args["message_id"]).get("at"))
    if boundary is None:
        return None
    facts = service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
    for fact in sorted(facts, key=lambda row: row["id"]):
        if (
            fact.get("case_id") != args.get("case_id")
            or fact.get("kind") != KIND_MAP.get(args["kind"], args["kind"])
            or fact.get("slot")
            or fact.get("field")
            or not opposing_preferences(fact.get("content", ""), args["quote"])
            or not sources_active(service, fact, ctx)
        ):
            continue
        try:
            fact = authorized_fact(service.memory, ctx.owner, ctx.subject, fact["id"], statuses=frozenset({"active"}))
            said_at = statement_instant(service.memory, ctx.owner, fact)
            valid_from = history_instant(fact.get("valid_from"))
            if said_at > min(boundary, service.clock.now()) or valid_from is None or valid_from > boundary:
                continue
            return fact
        except (EvidenceError, ScopeError):
            continue
    return None


def create_conflict_proposal(
    service: AgentToolsService,
    args: dict,
    ctx: ToolContext,
    source: dict,
    start: int,
    end: int,
    level: str,
    metadata: dict,
) -> dict[str, Any] | None:
    old = conflict_candidate(service, args, ctx)
    if old is None:
        return None
    incoming_ref = {
        "message_id": source["id"],
        "version": source["revision"],
        "start": start,
        "end": end,
        "quote": args["quote"],
    }
    refs = [incoming_ref, *old["source_refs"]]
    ident = "proposal_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    proposal = service.repo.put(
        ctx.owner,
        "proposal",
        ident,
        {
            "status": "pending",
            "proposal_type": "memory_conflict",
            "kind": args["kind"],
            "sensitivity": level,
            "categories": list(
                sensitivity_categories(args["quote"], source["content"], start, end, args["sensitivity"])
            ),
            "fact_metadata": dict(metadata, summary=args["summary"], requested_kind=args["kind"]),
            "summary": args["summary"],
            "target_fact_id": old["id"],
            "target_revision": old["revision"],
            "source_refs": refs,
            "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
            "fact_ids": [old["id"]],
            "inferred": False,
        },
        subject=ctx.subject,
        case_id=args.get("case_id"),
        expected_revision=0,
        operation_id=ctx.operation_id + ":conflict",
    )
    return {
        "write_status": "pending_confirmation",
        "id": proposal["id"],
        "kind": "proposal",
        "revision": proposal["revision"],
        "code": "memory2_possible_conflict",
    }


def checked_conflict(memory: MemoryService, owner: str, subject: str, proposal: dict) -> dict:
    if proposal["subject_id"] != subject:
        raise ScopeError("冲突提案不属于当前人物")
    if proposal.get("proposal_type") != "memory_conflict" or proposal["status"] != "pending":
        raise EvidenceError("冲突提案已失效")
    verify_originals(memory, owner, subject, proposal["source_refs"])
    old = authorized_fact(memory, owner, subject, proposal["target_fact_id"], statuses=frozenset({"active"}))
    if old["revision"] != proposal["target_revision"]:
        raise RevisionConflict("冲突对应的旧记忆已经变化")
    if old.get("case_id") != proposal.get("case_id"):
        raise ScopeError("冲突提案的事项不一致")
    cases = [old["case_id"]] if old.get("case_id") else []
    if old["id"] not in {row["id"] for row in memory.facts(owner, subject, cases)}:
        raise EvidenceError("冲突对应的旧记忆已不再有效")
    if not opposing_preferences(old["content"], proposal["source_refs"][0]["quote"]):
        raise EvidenceError("冲突提案与当前原话不一致")
    return old


def conflict_feedback(service: AgentToolsService, ctx: ToolContext, receipt: dict) -> dict[str, Any]:
    proposal = service.repo.get(ctx.owner, "proposal", receipt["id"])
    if proposal.get("case_id") is not None and proposal["case_id"] not in ctx.case_ids:
        raise ScopeError("冲突提案不属于当前事项范围")
    old = checked_conflict(service.memory, ctx.owner, ctx.subject, proposal)
    incoming = proposal["source_refs"][0]["quote"]
    return {
        "fact_id": old["id"],
        "summary": f"以前你说“{old['content']}”，现在说“{incoming}”，以哪个为准？",
        "detector": "exact_topic_opposite_preference",
        "vector_available": False,
    }

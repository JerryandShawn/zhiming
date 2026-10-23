"""Real memory mutations with source authority and body-free durable receipts."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.agent_tools_dates import event_metadata
from mingjing_core.application.agent_tools_policy import (
    CREDENTIAL,
    KIND_MAP,
    RULES,
    SENSITIVITIES,
    refusal,
    sensitivity,
    sensitivity_categories,
    source_span,
)
from mingjing_core.application.memory import SECRET
from mingjing_core.application.memory2_consent import categories_granted, category_authority_refs
from mingjing_core.application.memory2_merge import merge_written_fact
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import has_optout, hypothetical
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService


def checked_source(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
) -> tuple[dict[str, Any], int, int]:
    source = service.source(ctx, args["message_id"])
    start, end = source_span(source, args["quote"], args.get("start"), args.get("end"))
    service.check_span(ctx, source["id"], start, end)
    case_id = args.get("case_id")
    if case_id and (case_id not in ctx.case_ids or case_id not in source.get("case_ids", [])):
        raise ScopeError("事实事项不在本轮来源范围")
    return source, start, end


def source_ref(source: dict[str, Any], start: int, end: int) -> dict[str, Any]:
    return {
        "message_id": source["id"],
        "version": source["revision"],
        "start": start,
        "end": end,
        "quote": source["content"][start:end],
    }


def proposal(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
    start: int,
    end: int,
    level: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    ident = "proposal_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    row = service.repo.put(
        ctx.owner,
        "proposal",
        ident,
        {
            "status": "pending",
            "kind": args["kind"],
            "sensitivity": level,
            "categories": list(
                sensitivity_categories(args["quote"], source["content"], start, end, args["sensitivity"])
            ),
            "fact_metadata": dict(metadata, summary=args["summary"], requested_kind=args["kind"]),
            "health": bool(RULES["health"].search(source["content"][start:end])),
            "summary": args["summary"],
            "source_ids": [source["id"]],
            "source_refs": [source_ref(source, start, end)],
            "inferred": False,
        },
        subject=ctx.subject,
        case_id=args.get("case_id"),
        expected_revision=0,
        operation_id=ctx.operation_id + ":proposal",
    )
    return {
        "write_status": "pending_confirmation",
        "id": row["id"],
        "kind": "proposal",
        "revision": row["revision"],
        "code": "sensitive_confirmation",
    }


def save_memory(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
    start: int,
    end: int,
) -> dict[str, Any]:
    refused = refusal(source, args["quote"], start, end)
    if refused:
        return refused
    if SECRET.search(args["summary"]) or CREDENTIAL.search(args["summary"]):
        return {"write_status": "rejected", "code": "credential"}
    if hypothetical(source["content"], start, end) and args["kind"] != "concern":
        return {"write_status": "rejected", "code": "hypothetical"}
    level = sensitivity(args["quote"], source["content"], start, end, args["sensitivity"])
    if level == "secret":
        return {"write_status": "rejected", "code": "credential"}
    if level == "profile":
        return {"write_status": "needs_confirmation", "code": "profile_update_required"}
    metadata, pending = event_metadata(service, args, ctx, source)
    if pending:
        return pending
    categories = sensitivity_categories(args["quote"], source["content"], start, end, args["sensitivity"])
    if level in SENSITIVITIES and not categories_granted(service.memory, ctx.owner, ctx.subject, categories):
        return proposal(service, args, ctx, source, start, end, level, metadata)
    row = service.memory.save_fact(
        ctx.owner,
        ctx.subject,
        source["id"],
        args["quote"],
        KIND_MAP.get(args["kind"], args["kind"]),
        case_id=args.get("case_id"),
    )
    if row["write_status"] != "saved":
        return {"write_status": row["write_status"], "code": "memory_policy"}
    metadata.update(summary=args["summary"], requested_kind=args["kind"])
    if categories:
        refs, proofs = category_authority_refs(service.memory, ctx.owner, ctx.subject, categories)
        if proofs:
            metadata.update(
                source_refs=[*row["source_refs"], *(ref for ref in refs if ref not in row["source_refs"])],
                category_consent_ids=proofs,
            )
    if any(row.get(key) != value for key, value in metadata.items()):
        row = service.repo.update(
            ctx.owner,
            "fact",
            row["id"],
            metadata,
            expected_revision=row["revision"],
            operation_id=ctx.operation_id + ":metadata",
        )
    row, change_id = merge_written_fact(service, ctx, row)
    return {
        "write_status": "saved",
        "id": row["id"],
        "fact_id": row["id"],
        "kind": "fact",
        "revision": row["revision"],
        **({"ids": [change_id], "code": "memory2_merged"} if change_id else {}),
    }


def save_note(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    sources = [service.source(ctx, ident) for ident in dict.fromkeys(args["source_ids"])]
    if SECRET.search(args["summary"]) or CREDENTIAL.search(args["summary"]):
        return {"write_status": "rejected", "code": "credential"}
    if any(has_optout(source["content"]) or "无痕" in source["content"] for source in sources):
        return {"write_status": "stopped", "code": "source_optout"}
    refs = []
    for source in sources:
        service.check_span(ctx, source["id"], 0, len(source["content"]))
        refs.append({"message_id": source["id"], "version": source["revision"]})
    ident = "note_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    row = service.repo.put(
        ctx.owner,
        "note",
        ident,
        {
            "summary": args["summary"],
            "inferred": True,
            "assertion_status": "derived",
            "source_ids": [source["id"] for source in sources],
            "source_refs": refs,
        },
        subject=ctx.subject,
        expected_revision=0,
        operation_id=ctx.operation_id + ":note",
    )
    return {
        "write_status": "saved",
        "id": row["id"],
        "kind": "note",
        "revision": row["revision"],
    }


def forget_memory(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    source = service.source(ctx, args["message_id"])
    service.check_span(ctx, source["id"], 0, len(source["content"]))
    fact = service.repo.get(ctx.owner, "fact", args["fact_id"], include_deleted=True)
    if fact["subject_id"] != ctx.subject or fact.get("case_id") and fact["case_id"] not in ctx.case_ids:
        raise ScopeError("撤销目标不属于当前人物或事项")
    row = service.memory.retire_from_message(ctx.owner, fact["id"], source["id"], ctx.operation_id)
    return {
        "write_status": row["write_status"],
        "fact_id": fact["id"],
        "kind": "fact",
        "affected_ids": row.get("affected_fact_ids", [fact["id"]]),
    }


def execute_write(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    # Re-check authority before looking up cached receipts; withdrawn originals
    # can never resurrect a previous successful effect on replay.
    if name == "memory_write":
        source, start, end = checked_source(service, args, ctx)
        effect = partial(save_memory, service, args, ctx, source, start, end)
    elif name == "note_write":
        for ident in args["source_ids"]:
            source = service.source(ctx, ident)
            service.check_span(ctx, ident, 0, len(source["content"]))
        effect = partial(save_note, service, args, ctx)
    elif name == "memory_forget":
        service.source(ctx, args["message_id"])
        effect = partial(forget_memory, service, args, ctx)
    else:
        raise EvidenceError("未注册的写入工具")
    receipt = service.repo.mutation_request(ctx.owner, "agent_" + name, ctx.operation_id, args, effect)
    if receipt.get("code") == "memory2_merged":
        change = service.repo.get(ctx.owner, "proposal", receipt["ids"][0], include_deleted=True)
        if change["status"] != "applied":
            raise EvidenceError("原记忆合并已撤销或失效")
    if receipt.get("id") and receipt.get("kind") in {"fact", "note", "proposal"}:
        row = service.repo.get(ctx.owner, receipt["kind"], receipt["id"], include_deleted=True)
        if row["status"] in {"deleted", "stopped"}:
            raise EvidenceError("原写入结果已撤销")
    status = receipt["write_status"]
    return ToolResult(
        ok=status in {"saved", "deleted", "stopped"},
        receipt=receipt,
        data={"write_status": status},
        summary="记忆操作状态：" + status,
    )

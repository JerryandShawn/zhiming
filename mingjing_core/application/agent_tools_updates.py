"""Current-source corrections and confirmation requests; never writes profile values."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.agent.tools.computation_parameters import MemoryUpdate, ProfileUpdateRequest
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_memory import checked_source, source_ref
from mingjing_core.application.agent_tools_policy import CREDENTIAL, SENSITIVITIES, refusal, sensitivity
from mingjing_core.application.memory import SECRET, explicit_save_authorization
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.policy import authorization_clause, hypothetical
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

UPDATE_NAMES = frozenset({"memory_update", "profile_update_request"})


def request_proposal(
    service: AgentToolsService, ctx: ToolContext, source: dict[str, Any], start: int, end: int, data: dict[str, Any]
) -> dict[str, Any]:
    ident = "proposal_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    row = service.repo.put(
        ctx.owner,
        "proposal",
        ident,
        dict(
            data,
            status="pending",
            source_ids=[source["id"]],
            source_refs=[source_ref(source, start, end)],
            inferred=False,
        ),
        subject=ctx.subject,
        expected_revision=0,
        operation_id=ctx.operation_id + ":proposal",
    )
    return {
        "write_status": "pending_confirmation",
        "id": row["id"],
        "kind": "proposal",
        "revision": row["revision"],
        "code": data["kind"],
    }


def correction_target(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    old = service.repo.get(ctx.owner, "fact", args["fact_id"])
    if old["subject_id"] != ctx.subject or old.get("case_id") and old["case_id"] not in ctx.case_ids:
        raise ScopeError("更正目标不属于当前人物或事项")
    if old["revision"] != args["expected_revision"]:
        raise RevisionConflict("更正前事实已变化")
    if old["status"] != "active" or service.repo.is_revoked(ctx.owner, "fact", old["id"]):
        raise EvidenceError("已失效事实不能被更正工具复活")
    return old


def correction_policy(
    old: dict[str, Any], source: dict[str, Any], quote: str, start: int, end: int
) -> tuple[str, bool, bool]:
    level = sensitivity(quote, source["content"], start, end)
    old_level = sensitivity(old["content"], old["content"], 0, len(old["content"]))
    if level == "normal" and old_level in SENSITIVITIES:
        level = old_level
    profile = bool(old.get("field")) or old.get("kind") == "profile" or level == "profile"
    authorized = explicit_save_authorization(authorization_clause(source["content"], start, end))
    return level, profile, authorized


def correct_memory(
    service: AgentToolsService, args: dict[str, Any], ctx: ToolContext, source: dict[str, Any], start: int, end: int
) -> dict[str, Any]:
    old = correction_target(service, args, ctx)
    retained = service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
    if old.get("content") not in source["content"] and {row["id"] for row in retained} != {old["id"]}:
        return request_proposal(
            service,
            ctx,
            source,
            start,
            end,
            {
                "kind": "correction_target_confirmation",
                "target_fact_id": old["id"],
                "target_revision": old["revision"],
                "summary": args["summary"],
            },
        )
    if hypothetical(source["content"], start, end):
        return {"write_status": "rejected", "code": "hypothetical"}
    level, profile, authorized = correction_policy(old, source, args["quote"], start, end)
    if profile or level in SENSITIVITIES and not authorized:
        return request_proposal(
            service,
            ctx,
            source,
            start,
            end,
            {
                "kind": "profile_update_required" if profile else "sensitive_correction",
                "target_fact_id": old["id"],
                "target_revision": old["revision"],
                "summary": args["summary"],
                "sensitivity": level,
            },
        )
    row = service.memory.correct_fact(
        ctx.owner,
        old["id"],
        source["id"],
        args["quote"],
        expected_revision=args["expected_revision"],
        operation_id=ctx.operation_id + ":correction",
    )
    if row.get("write_status") != "saved":
        return {"write_status": row["write_status"], "code": "memory_policy"}
    row = service.repo.update(
        ctx.owner,
        "fact",
        row["id"],
        {"summary": args["summary"]},
        expected_revision=row["revision"],
        operation_id=ctx.operation_id + ":metadata",
    )
    return {"write_status": "saved", "id": row["id"], "fact_id": row["id"], "kind": "fact", "revision": row["revision"]}


def apply_update(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
    start: int,
    end: int,
) -> dict[str, Any]:
    refused = refusal(source, args["quote"], start, end)
    if refused:
        return refused
    if (
        SECRET.search(args["quote"])
        or CREDENTIAL.search(args["quote"])
        or (name == "memory_update" and (SECRET.search(args["summary"]) or CREDENTIAL.search(args["summary"])))
    ):
        return {"write_status": "rejected", "code": "credential"}
    if name == "memory_update":
        return correct_memory(service, args, ctx, source, start, end)
    return request_proposal(
        service,
        ctx,
        source,
        start,
        end,
        {
            "kind": "profile_update_request",
            "fields": list(dict.fromkeys(args["fields"])),
            "expected_profile_revision": service.repo.get_revision(ctx.owner),
        },
    )


def execute_update(service: AgentToolsService, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolResult:
    if name not in UPDATE_NAMES or name != ctx.name:
        raise EvidenceError("更正工具身份无效")
    model = MemoryUpdate if name == "memory_update" else ProfileUpdateRequest
    args = model.model_validate(arguments).model_dump()
    if tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp:
        raise EvidenceError("更正工具参数与持久步骤不符")
    if ctx.private:
        return ToolResult(
            ok=False, receipt={"write_status": "stopped", "code": "incognito"}, summary="无痕模式未写入长期资料"
        )
    if ctx.crisis:
        raise ScopeError("危机模式下不修改资料")
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        source, start, end = checked_source(service, args, ctx)
        effect = partial(apply_update, service, name, args, ctx, source, start, end)
        receipt = service.repo.mutation_request(ctx.owner, "agent_" + name, ctx.operation_id, args, effect)
        if receipt.get("id"):
            row = service.repo.get(ctx.owner, receipt["kind"], receipt["id"], include_deleted=True)
            if row["status"] in {"deleted", "stopped", "superseded"}:
                raise EvidenceError("原更正或确认请求已失效")
    return ToolResult(
        ok=receipt["write_status"] == "saved",
        receipt=receipt,
        data={"write_status": receipt["write_status"]},
        summary="更正或资料确认状态：" + receipt["write_status"],
    )

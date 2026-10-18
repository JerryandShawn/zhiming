"""Case effects preserve current user originals instead of manufacturing messages."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_memory import checked_source, source_ref
from mingjing_core.application.agent_tools_policy import refusal, sensitivity
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.policy import hypothetical
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService


def selected_case(service: AgentToolsService, ctx: ToolContext, ident: str) -> dict[str, Any]:
    row = service.repo.get(ctx.owner, "case", ident)
    if row["subject_id"] != ctx.subject or ident not in ctx.case_ids:
        raise ScopeError("事项不属于当前人物或未被本轮选中")
    return row


def case_source(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
) -> tuple[dict[str, Any], int, int, dict[str, Any] | None]:
    quote = args.get("quote", args.get("content", ""))
    source, start, end = checked_source(service, dict(args, quote=quote, case_id=args["id"]), ctx)
    refused = refusal(source, quote, start, end)
    if refused:
        return source, start, end, refused
    if hypothetical(source["content"], start, end):
        return source, start, end, {"write_status": "rejected", "code": "hypothetical"}
    level = sensitivity(quote, source["content"], start, end)
    if level != "normal":
        code = "credential" if level == "secret" else "sensitive_confirmation"
        return source, start, end, {"write_status": "needs_confirmation", "code": code}
    return source, start, end, None


def mutate_case(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> dict[str, Any]:
    row = selected_case(service, ctx, args["id"])
    if row["revision"] != args["expected_revision"]:
        raise RevisionConflict("事项已更新，请刷新后操作")
    source, start, end, refused = case_source(service, args, ctx)
    if refused:
        return refused
    ref = source_ref(source, start, end)
    if name == "case_update":
        changes = {key: value for key, value in args["changes"].items() if value is not None}
        if not changes:
            raise EvidenceError("事项修改不能为空")
        for key in ("title", "goal"):
            if key in changes and changes[key] not in args["quote"]:
                raise EvidenceError("事项标题和目标必须逐字来自用户原话")
        payload = {key: value for key, value in changes.items() if key in {"title", "status"}}
        if "goal" in changes:
            payload["state"] = dict(row.get("state", {}), goal=changes["goal"])
        payload["source_refs"] = list(row.get("source_refs", [])) + [ref]
        field_refs = dict(row.get("field_source_refs", {}))
        for field in ("title", "goal"):
            field_refs.setdefault(field, list(row.get("source_refs", [])))
            if field in changes:
                offset = source["content"].index(changes[field], start, end)
                field_refs[field] = [source_ref(source, offset, offset + len(changes[field]))]
        payload["field_source_refs"] = field_refs
        result = service.repo.update(
            ctx.owner,
            "case",
            row["id"],
            payload,
            expected_revision=row["revision"],
            operation_id=ctx.operation_id + ":case",
        )
        return {"write_status": "saved", "id": result["id"], "kind": "case", "revision": result["revision"]}
    ident = "event_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    result = service.repo.put(
        ctx.owner,
        "feedback",
        ident,
        {
            "kind": args["kind"],
            "content": args["content"],
            "source_refs": [ref],
            "source_ids": [source["id"]],
            "occurred_at": source["at"],
            "assertion_status": "user_asserted",
        },
        subject=ctx.subject,
        case_id=row["id"],
        expected_revision=0,
        operation_id=ctx.operation_id + ":event",
    )
    return {"write_status": "saved", "id": result["id"], "kind": "feedback", "revision": result["revision"]}


def execute_case(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if name != ctx.name or tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp or ctx.crisis:
            raise ScopeError("当前模式不可使用事项工具")
        if name == "case_list":
            rows = service.repo.list(ctx.owner, "case", subject=ctx.subject, limit=100)
            return ToolResult(
                ok=True,
                data={
                    "cases": [
                        {"id": row["id"], "title": row["title"], "status": row["status"], "revision": row["revision"]}
                        for row in rows
                    ],
                    "limit": 100,
                },
                summary="事项索引查询已完成",
            )
        if name not in {"case_update", "case_add_event"}:
            raise EvidenceError("未注册的事项工具")
        if ctx.private:
            return ToolResult(ok=False, data={"code": "incognito"}, summary="无痕模式未修改长期事项")
        selected_case(service, ctx, args["id"])
        case_source(service, args, ctx)
        receipt = service.repo.mutation_request(
            ctx.owner,
            "agent_" + name,
            ctx.operation_id,
            args,
            partial(mutate_case, service, name, args, ctx),
        )
        return ToolResult(
            ok=receipt["write_status"] == "saved", receipt=receipt, summary="事项操作状态：" + receipt["write_status"]
        )

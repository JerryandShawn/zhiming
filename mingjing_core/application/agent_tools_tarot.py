"""V4 tarot tools preserve the real service's fixed deck and explicit reveal flow."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.adapters.tarot import TarotService
from mingjing_core.application.agent_tarot_lineage import operation_source_refs, save_tarot_snapshot
from mingjing_core.application.agent_tool_persistence import privacy_refusal
from mingjing_core.application.agent_tools_contracts import (
    ToolContext,
    ToolResult,
    tool_input_fingerprint,
)
from mingjing_core.application.agent_tools_memory import checked_source
from mingjing_core.application.agent_tools_policy import CREDENTIAL, refusal
from mingjing_core.application.agent_tools_tarot_guard import (
    explicit_redraw,
    recent_draw,
    tarot_mode,
    validate_draw_source,
)
from mingjing_core.application.memory import SECRET
from mingjing_core.domain.contracts import EvidenceError, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService


def start_source(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> tuple[dict[str, Any], int, int]:
    return checked_source(service, dict(args, quote=args["question"]), ctx)


def draw_case(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
) -> str:
    ident = args["case_id"] or (ctx.case_ids[0] if len(ctx.case_ids) == 1 else None)
    if ident:
        if ident not in ctx.case_ids or ident not in source.get("case_ids", []):
            raise ScopeError("塔罗事项不属于本轮来源范围")
        return ident
    if ctx.case_ids:
        raise EvidenceError("多个事项需要先确认本次抽牌属于哪一项")
    row = service.memory.create_case(
        ctx.owner,
        ctx.subject,
        args["question"][:120],
        goal=args["question"],
        message_id=source["id"],
        operation_id=ctx.operation_id + ":case",
    )
    return row["id"]


def start_effect(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
) -> dict[str, Any]:
    source, start, end = start_source(service, args, ctx)
    stopped = refusal(source, args["question"], start, end)
    # Quoted questions are legitimate inputs to a requested draw, but opt-out
    # still blocks durable state and quoted words cannot authorize a redraw.
    if stopped and stopped["code"] != "quoted_speech":
        return stopped
    if SECRET.search(args["question"]) or CREDENTIAL.search(args["question"]):
        return {"write_status": "rejected", "code": "credential"}
    if args["explicit_new"] and not explicit_redraw(source["content"]):
        return {"write_status": "needs_confirmation", "code": "explicit_redraw_required"}
    for option in args["options"].values():
        if option not in source["content"]:
            raise EvidenceError("比较选项必须来自用户原话")
    recent, overflow = recent_draw(service, ctx, args["question"])
    if recent and not args["explicit_new"]:
        return {"write_status": "recent_draw_exists", "code": "recent_draw_exists", "draw_id": recent["id"]}
    if overflow:
        return {"write_status": "needs_confirmation", "code": "recent_draw_check_limit"}
    ident = draw_case(service, args, ctx, source)
    snapshot = {
        "question_message_id": source["id"],
        "source_ids": [source["id"]],
        "source_refs": operation_source_refs(service, ctx, args, source, start, end),
        "thread_id": ctx.thread_id,
    }
    result = TarotService(service.repo).create_draw(
        ctx.owner,
        subject_id=ctx.subject,
        case_id=ident,
        question=args["question"],
        spread_id=args["spread_id"],
        draw_source=args["draw_source"],
        reversals=args["reversals"],
        options=args["options"],
        context_snapshot=snapshot,
        idempotency_key=ctx.operation_id,
        stage="v4:" + ctx.run_id,
        explicit_new=args["explicit_new"],
    )
    return {"write_status": "saved", "kind": "draw", "draw_id": result["draw"]["id"]}


def execute_tarot(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if (
            name != ctx.name
            or tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp
            or ctx.crisis
            or name not in {"tarot_start", "tarot_read"}
        ):
            raise ScopeError("塔罗工具身份或模式不符")
        if name == "tarot_start" and ctx.private:
            return ToolResult(ok=False, data={"code": "incognito"}, summary="无痕模式未建立长期牌阵")
        if stopped := privacy_refusal(service, name, args, ctx):
            return stopped
        mode = tarot_mode(service, ctx)
        if name != mode:
            raise EvidenceError("请先选中并揭示固定牌阵，重抽需要明确的新请求")
        if name == "tarot_read":
            actual = service.repo.fetch_run(ctx.owner, ctx.run_id)["request"].get("draw_id")
            if args["draw_id"] != actual:
                raise ScopeError("只能读取本轮真实选中的固定牌阵")
            draw = TarotService(service.repo).get_for_reading(ctx.owner, actual)
            validate_draw_source(service, ctx, draw)
            result = ToolResult(ok=True, data={"draw": draw}, summary="固定牌面与牌义已读取")
            save_tarot_snapshot(service, ctx, args, result)
            return result
        start_source(service, args, ctx)
        receipt = service.repo.mutation_request(
            ctx.owner,
            "agent_tarot_start",
            ctx.operation_id,
            args,
            partial(start_effect, service, args, ctx),
        )
        status = receipt["write_status"]
        if status == "saved":
            draw = TarotService(service.repo).get(ctx.owner, receipt["draw_id"])
            validate_draw_source(service, ctx, draw)
            result = ToolResult(ok=True, data={"draw": draw}, receipt=receipt, summary="固定牌阵已建立，请选择或揭牌")
            save_tarot_snapshot(service, ctx, args, result)
            return result
        return ToolResult(
            ok=False,
            data={"code": receipt["code"], "draw_id": receipt.get("draw_id")},
            receipt=receipt,
            summary="近24小时已有同类牌阵" if status == "recent_draw_exists" else "抽牌需要先确认",
        )

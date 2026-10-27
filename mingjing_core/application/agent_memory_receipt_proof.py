"""An event needs an exact acknowledged mutation and currently authorized entity."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from pydantic import ValidationError

from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.agent.loop_codec import verified_versions
from mingjing_core.agent.tools.computation_parameters import MemoryUpdate, ProfileUpdateRequest
from mingjing_core.agent.tools.parameters import MemoryForget, MemoryWrite
from mingjing_core.application.agent_thread_scope import assert_thread, thread_id
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_memory import checked_source
from mingjing_core.application.agent_tools_policy import sensitivity
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint

MODELS = {
    "memory_write": MemoryWrite,
    "memory_forget": MemoryForget,
    "memory_update": MemoryUpdate,
    "profile_update_request": ProfileUpdateRequest,
}


def _identity(run: dict, step: JournalStep, ctx: ToolContext) -> None:
    if (
        (ctx.owner, ctx.run_id, ctx.subject, ctx.epoch, ctx.lease_token, ctx.thread_id)
        != (run["owner"], run["id"], run["subject"], run["retry_epoch"], run["lease_token"], thread_id(run))
        or (step.owner, step.run_id, step.subject, step.epoch, step.seq, step.name, step.input_fp, step.lease_token)
        != (ctx.owner, ctx.run_id, ctx.subject, ctx.epoch, ctx.seq, ctx.name, ctx.input_fp, ctx.lease_token)
        or step.kind != "tool"
        or ctx.private
        or ctx.crisis
    ):
        raise ScopeError("记忆回执不属于当前受信工具步骤")


def _arguments(name: str, raw: dict, ctx: ToolContext) -> dict:
    try:
        values = MODELS[name].model_validate(raw).model_dump()
    except (KeyError, ValidationError, TypeError, ValueError):
        raise EvidenceError("记忆回执缺少有效的原工具输入") from None
    if tool_input_fingerprint(name, values, ctx.source_versions) != ctx.input_fp:
        raise EvidenceError("记忆回执输入与持久步骤不符")
    return values


def _acknowledged(
    repo: PostgresRepository, connection: Any, step: JournalStep, result: ToolResult, values: dict
) -> dict:
    row = Journal(repo, step.owner)._read(connection, step.run_id, step.epoch, step.seq)
    if (
        not row
        or (row["kind"], row["name"], row["input_fp"]) != ("tool", step.name, step.input_fp)
        or row["status"] != "completed"
        or row["finished_at"] is None
        or row["error_code"] is not None
        or not isinstance(row["output"], dict)
        or fingerprint(row["output"]) != fingerprint(result.model_dump())
    ):
        raise EvidenceError("记忆回执缺少真实完成记录")
    mutation = connection.execute(
        sql.SQL("SELECT fingerprint,receipt FROM {} WHERE owner=%s AND operation=%s AND request_key=%s").format(
            repo.table("core_mutation_requests")
        ),
        (step.owner, "agent_" + step.name, step.operation_id),
    ).fetchone()
    if (
        not mutation
        or mutation["fingerprint"] != fingerprint(values)
        or fingerprint(mutation["receipt"]) != fingerprint(result.receipt)
    ):
        raise EvidenceError("记忆回执缺少精确写入收据")
    return mutation["receipt"]


def _source(service: AgentToolsService, ctx: ToolContext, values: dict) -> tuple[dict, int, int]:
    if ctx.name != "memory_forget":
        return checked_source(service, values, ctx)
    source = service.source(ctx, values["message_id"])
    service.check_span(ctx, source["id"], 0, len(source["content"]))
    return source, 0, len(source["content"])


def _entity(service: AgentToolsService, current: dict, ctx: ToolContext, receipt: dict, result: ToolResult) -> dict:
    status = receipt.get("write_status")
    forgotten = ctx.name == "memory_forget"
    kind = "proposal" if status == "pending_confirmation" else "fact"
    ident = receipt.get("fact_id") if forgotten else receipt.get("id")
    if (
        receipt.get("kind") != kind
        or not isinstance(ident, str)
        or not ident
        or receipt.get("fact_id", ident) != ident
        or receipt.get("id", ident) != ident
        or result.ends_turn
        or result.ok is not (status in {"saved", "deleted", "stopped"})
    ):
        raise EvidenceError("记忆回执实体或状态不符")
    row = service.repo.get(ctx.owner, kind, ident, include_deleted=True)
    if row["subject_id"] != ctx.subject or row.get("case_id") and row["case_id"] not in ctx.case_ids:
        raise ScopeError("记忆回执实体不属于当前人物或事项")
    if forgotten:
        if row["status"] != status or not service.repo.is_revoked(ctx.owner, "fact", ident):
            raise EvidenceError("遗忘回执没有实际撤销证明")
        return row
    if type(receipt.get("revision")) is not int or row["revision"] != receipt["revision"]:
        raise EvidenceError("记忆回执的实体版本已经改变")
    expected = "pending" if kind == "proposal" else "active"
    if row["status"] != expected or kind == "fact" and row.get("consent") != "granted":
        raise EvidenceError("记忆回执实体已经失效")
    _, records = verified_versions(service, current, ctx.name, result)
    if not any(record["kind"] == kind and record["id"] == ident for record in records):
        raise EvidenceError("记忆回执缺少有效来源闭包")
    return row


def _payload(
    service: AgentToolsService, ctx: ToolContext, receipt: dict, row: dict, source: dict, start: int, end: int
) -> dict:
    status = receipt["write_status"]
    if ctx.name == "memory_forget":
        return {"fact_id": row["id"], "write_status": "undone", "summary": "已撤销这条记忆", "sensitive": True}
    if not any(
        ref.get("message_id") == source["id"]
        and ref.get("version") == source["revision"]
        and ref.get("start") == start
        and ref.get("end") == end
        and ref.get("quote") == source["content"][start:end]
        for ref in row.get("source_refs", [])
    ):
        raise EvidenceError("记忆回执实体不属于实际本轮原话")
    level = sensitivity(source["content"][start:end], source["content"], start, end)
    if level == "secret":
        raise EvidenceError("凭据不能生成记忆成功回执")
    sensitive = level != "normal" or bool(row.get("field"))
    if old_id := row.get("supersedes_id"):
        old = service.repo.get(ctx.owner, "fact", old_id, include_deleted=True)
        if old["subject_id"] != ctx.subject:
            raise ScopeError("更正回执原人物不符")
        sensitive = (
            sensitive
            or not old.get("content")
            or sensitivity(old["content"], old["content"], 0, len(old["content"])) != "normal"
        )
    if status == "pending_confirmation":
        sensitive = sensitive or row.get("sensitivity") != "normal" or row.get("kind") == "profile_update_request"
        return {
            "proposal_id": row["id"],
            "write_status": "pending_confirm",
            "summary": "这条记忆等待你确认",
            "sensitive": sensitive,
        }
    return {"fact_id": row["id"], "write_status": "saved", "summary": "已保存这条记忆", "sensitive": sensitive}


def project_receipt(
    repo: PostgresRepository,
    connection: Any,
    run: dict,
    step: JournalStep,
    result: ToolResult,
    arguments: dict,
    context: ToolContext,
) -> dict | None:
    if step.name not in MODELS or not result.receipt:
        return None
    status = result.receipt.get("write_status")
    if status in {"rejected", "needs_confirmation", "stopped"} and not any(
        result.receipt.get(key) for key in ("id", "fact_id")
    ):
        return None
    allowed = {"deleted", "stopped"} if step.name == "memory_forget" else {"saved", "pending_confirmation"}
    if status not in allowed:
        raise EvidenceError("记忆回执状态尚无可信公开投影")
    _identity(run, step, context)
    service = AgentToolsService(repo)
    current = Journal(repo, run["owner"])._leased(connection, run)
    assert_thread(repo, current)
    service.authority(connection, context)
    values = _arguments(step.name, arguments, context)
    receipt = _acknowledged(repo, connection, step, result, values)
    source, start, end = _source(service, context, values)
    row = _entity(service, current, context, receipt, result)
    return _payload(service, context, receipt, row, source, start, end)

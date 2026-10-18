"""Clarification slots persist counters without storing model questions as facts."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_policy import source_policy
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.memory.policy import mask_quoted
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.repositories.postgres import PostgresRepository

DECLINE = re.compile(
    r"不想说(?!谎)|不想回答|不方便说|暂时不说|不愿意透露|别再问|你别问|先别问|不要再问"
    r"|你先说|(?:随便|随你|不知道|不清楚|没想好)[吧了啊呀嗯\s]*[。！!，,；;]*$"
)
CANCEL_DECLINE = re.compile(r"(?:不是|并非|没有)(?:不想说|不想回答|不知道|不清楚|不愿意透露)")
HYPOTHETICAL = re.compile(r"假如|假设|如果|举个例子|比如说|[？?]")


def declines_answer(text: str) -> bool:
    visible = mask_quoted(text)
    if HYPOTHETICAL.search(visible):
        return False
    return DECLINE.search(CANCEL_DECLINE.sub(" ", visible)) is not None


def thread_row(repo: PostgresRepository, owner: str, subject: str, thread: str) -> dict[str, Any] | None:
    try:
        row = repo.get(owner, "thread", thread)
    except ScopeError:
        return None
    if row["subject_id"] != subject:
        raise ScopeError("澄清线程不属于当前人物")
    return row


def live_slots(row: dict[str, Any] | None, now: datetime) -> list[dict[str, Any]]:
    values = row.get("clarify_slots", []) if row else []
    if not isinstance(values, list) or len(values) > 100:
        raise EvidenceError("澄清槽位记录无效")
    result = []
    for item in values:
        if (
            not isinstance(item, dict)
            or item.get("status") not in {"unfilled", "filled", "declined", "conflict"}
            or type(item.get("asked_count")) is not int
            or item["asked_count"] < 0
            or not isinstance(item.get("slot"), str)
            or history_instant(item.get("last_asked_at")) is None
        ):
            raise EvidenceError("澄清槽位状态无效")
        expires = history_instant(item.get("expires_at"))
        if expires is None:
            raise EvidenceError("澄清槽位过期时间无效")
        if expires > now:
            result.append(dict(item))
    return result


def save_slots(
    repo: PostgresRepository,
    owner: str,
    subject: str,
    thread: str,
    row: dict[str, Any] | None,
    changes: dict[str, Any],
    operation_id: str,
) -> dict[str, Any]:
    if row is not None:
        return repo.update(
            owner, "thread", thread, changes, expected_revision=row["revision"], operation_id=operation_id
        )
    return repo.put(owner, "thread", thread, changes, subject=subject, expected_revision=0, operation_id=operation_id)


def ask_effect(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
) -> dict[str, Any]:
    now = service.clock.now().astimezone(UTC)
    row = thread_row(service.repo, ctx.owner, ctx.subject, ctx.thread_id)
    slots = live_slots(row, now)
    last = row.get("last_clarification", {}) if row else {}
    if (last.get("run_id"), last.get("epoch")) == (ctx.run_id, ctx.epoch):
        return {"write_status": "rejected", "code": "question_already_asked"}
    existing = next((item for item in slots if item["slot"] == args["slot"]), None)
    if existing and existing["asked_count"] >= 2:
        return {"write_status": "rejected", "code": "slot_exhausted"}
    if existing and existing["status"] == "declined":
        return {"write_status": "rejected", "code": "slot_declined"}
    if existing and existing["status"] == "filled" and "确认" not in args["why"]:
        return {"write_status": "rejected", "code": "slot_already_filled"}
    source = service.repo.fetch_run(ctx.owner, ctx.run_id)["request"]["source_message_id"]
    slot = dict(
        existing or {},
        slot=args["slot"],
        status="conflict" if existing and "确认" in args["why"] else "unfilled",
        asked_count=(existing["asked_count"] if existing else 0) + 1,
        last_asked_at=now.isoformat(),
        answer_message_id=None,
        question_message_id=source,
        expires_at=(now + timedelta(days=7)).isoformat(),
    )
    slots = [item for item in slots if item["slot"] != args["slot"]] + [slot]
    result = save_slots(
        service.repo,
        ctx.owner,
        ctx.subject,
        ctx.thread_id,
        row,
        {"clarify_slots": slots, "last_clarification": {"run_id": ctx.run_id, "epoch": ctx.epoch}},
        ctx.operation_id + ":clarification",
    )
    return {
        "write_status": "saved",
        "status": "asked",
        "id": result["id"],
        "kind": "thread",
        "revision": result["revision"],
    }


def execute_clarification(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if name != ctx.name or tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp or ctx.crisis:
            raise ScopeError("当前模式不可使用提问工具")
        if name == "present_options":
            return ToolResult(ok=True, data={"options": args["options"]}, summary="决策选项已生成")
        if name != "ask_user":
            raise EvidenceError("未注册的提问工具")
        actual = service.repo.fetch_run(ctx.owner, ctx.run_id)["request"]["source_message_id"]
        source = service.source(ctx, actual)
        service.check_span(ctx, actual, 0, len(source["content"]))
        receipt = service.repo.mutation_request(
            ctx.owner,
            "agent_ask_user",
            ctx.operation_id,
            args,
            partial(ask_effect, service, args, ctx),
        )
        asked = receipt.get("status") == "asked"
        data = (
            {"asked": args}
            if asked
            else {
                "error": receipt["code"],
                "guidance": "已经询问或用户不愿回答，请带着明确假设回答",
            }
        )
        return ToolResult(
            ok=asked,
            data=data,
            receipt=receipt,
            ends_turn=asked,
            summary="澄清提问已生成" if asked else "澄清提问未继续",
        )


def answer_authority(
    repo: PostgresRepository,
    connection: Any,
    run: dict[str, Any],
    clock: Clock,
) -> dict[str, Any]:
    owner = run.get("owner", run.get("owner_user_id"))
    if not isinstance(owner, str):
        raise ScopeError("澄清回复需要受信运行")
    row = repo._leased(connection, owner, run["id"], run["lease_token"])
    if row["retry_epoch"] != run.get("retry_epoch") or row["runtime"] != "v4" or row["cancel_requested_at"] is not None:
        raise LeaseConflict("澄清回复运行已失效")
    if row["deadline_at"] is not None and row["deadline_at"] <= clock.now():
        raise LeaseConflict("澄清回复执行时间已结束")
    if row["subject"] != run.get("subject", run.get("subject_id")):
        raise ScopeError("澄清回复人物不符")
    repo.assert_scope(owner, row["subject"])
    return row


def answer_changes(
    slots: list[dict[str, Any]],
    source: dict[str, Any],
) -> list[dict[str, Any]]:
    instant = history_instant(source["at"])
    if instant is None:
        raise EvidenceError("澄清回复来源时间无效")
    pending = [
        item
        for item in slots
        if item["status"] in {"unfilled", "conflict"}
        and not item.get("answer_message_id")
        and item.get("question_message_id") != source["id"]
        and history_instant(item["last_asked_at"]) <= instant
    ]
    if not pending or not source["content"].strip():
        return slots
    target = max(pending, key=lambda item: item["last_asked_at"])
    status = "declined" if declines_answer(source["content"]) else "filled"
    return [dict(item, status=status, answer_message_id=source["id"]) if item is target else item for item in slots]


def apply_clarification_answer(
    repo: PostgresRepository,
    run: dict[str, Any],
    clock: Clock | None = None,
) -> int:
    """Called once from prepare after claim; only the persisted source can answer."""
    clock = clock or get_clock()
    owner = run.get("owner", run.get("owner_user_id"))
    with repo.transaction(owner) as connection:
        current = answer_authority(repo, connection, run, clock)
        thread = current["thread_id"] or current["request"].get("thread_id") or "life:" + current["subject"]
        row = thread_row(repo, owner, current["subject"], thread)
        if row is None:
            return 0
        ident = current["request"].get("source_message_id")
        if not isinstance(ident, str):
            raise EvidenceError("澄清回复缺少受信来源")
        source = MemoryService(repo).get_source(owner, ident)
        source_policy(source, current["subject"], thread)
        for revocation in repo.revocations(owner):
            span = revocation["metadata"]
            if (
                revocation["kind"] == "message"
                and revocation["entity_id"] == ident
                or revocation["kind"] == "source_span"
                and span.get("message_id") == ident
            ):
                raise EvidenceError("澄清回复来源已撤销")
        slots = live_slots(row, clock.now())
        updated = answer_changes(slots, source)
        if updated == slots:
            return 0
        save_slots(
            repo,
            owner,
            current["subject"],
            thread,
            row,
            {"clarify_slots": updated},
            f"run:{current['id']}:e{current['retry_epoch']}:clarification-answer",
        )
        return 1

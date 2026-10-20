"""A mandatory privacy card is journaled through the real ask_user tool."""

from typing import Any

from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.application.incognito_reminders import CONFIRM_QUESTION
from mingjing_core.domain.contracts import EvidenceError


def ask_privacy(cycle: Any, request_id: str) -> ToolResult:
    service, ctx = cycle.registry.service, cycle._context()
    thread = service.repo.get(ctx.owner, "thread", ctx.thread_id)
    pending = thread.get("reminder_confirmation", {})
    if (
        not ctx.private
        or pending.get("request_id") != request_id
        or pending.get("state") != "pending"
        or pending.get("source_id") != cycle.run["request"]["source_message_id"]
    ):
        raise EvidenceError("无痕提醒提问缺少当前真实请求")
    args = dict(
        question=CONFIRM_QUESTION,
        options=["可以", "不保存"],
        allow_free_text=True,
        why="提醒需要单独保存内容与时间才能触发",
        slot="无痕提醒保存",
        changes_conclusion="是否保存本条提醒",
    )
    fp = cycle.registry.fingerprint("ask_user", args, source_versions=cycle.frozen.injected_versions)
    step = cycle.journal.next_or_replay(cycle.run, kind="tool", name="ask_user", input_fp=fp)
    if step.completed:
        result = ToolResult.model_validate(step.output)
    else:
        result = cycle.registry.execute("ask_user", args, cycle._context(step))
        cycle.journal.complete(step, result.model_dump())
    if not result.ok or not result.ends_turn:
        raise EvidenceError("无痕提醒确认未能产生真实提问步骤")
    cycle._register("ask_user", result)
    if result.receipt:
        cycle.receipts.append(result.receipt)
    cycle.asked = result.data["asked"]
    return result

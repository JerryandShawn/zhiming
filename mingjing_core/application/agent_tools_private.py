"""Incognito reminder intent produces one real ask_user step, never silent consent."""

from typing import Any

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.incognito_reminders import IncognitoReminderService
from mingjing_core.domain.contracts import EvidenceError


def private_reminder(service: Any, args: dict, ctx: ToolContext) -> ToolResult:
    reminders = IncognitoReminderService(service.repo, clock=service.clock)
    with service.repo.transaction(ctx.owner) as connection:
        reminders.threads._lock(connection, ctx.owner, ctx.thread_id)
        run = service.authority(connection, ctx)
        source = service.source(ctx, args["message_id"])
        if not args["quote"] or args["quote"] not in source["content"]:
            raise EvidenceError("提醒引用必须来自本轮用户原话")
        service.check_span(ctx, source["id"], 0, len(source["content"]))
        result = reminders.begin(ctx.owner, service.repo._run(run), text=args["text"], due_at=args["due_at"])
        thread = reminders.threads.get(ctx.owner, ctx.thread_id, subject=ctx.subject)
        pending = thread.get("reminder_confirmation", {})
        current_request = pending.get("source_id") == source["id"] and pending.get("state") == "pending"
        return ToolResult(
            ok=True,
            data={
                "status": result["status"],
                **({"privacy_confirmation": result["request_id"]} if current_request else {}),
            },
            summary="提醒尚未保存，需要单独确认" if current_request else "已有提醒确认，不重复询问",
        )


def consume_private_answer(repo: Any, run: dict) -> dict | None:
    if not (run.get("thread_id") or "").startswith("incognito:"):
        return None
    service = IncognitoReminderService(repo)
    thread = service.threads.get(run["owner"], run["thread_id"], subject=run["subject"])
    pending = thread.get("reminder_confirmation", {})
    if (
        pending.get("state") in {"saved", "rejected"}
        and pending.get("answer_source_id") == run["request"]["source_message_id"]
        and pending.get("confirmation_run_id") == run["id"]
    ):
        return {"write_status": pending["state"], "id": pending.get("reminder_id"), "kind": "reminder"}
    if pending.get("state") != "pending" or pending.get("source_id") == run["request"]["source_message_id"]:
        return None
    return service.confirm(run["owner"], run, request_id=pending["request_id"])

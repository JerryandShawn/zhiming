"""Scheduling writes local rows only; delivery remains a later-stage service."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult, tool_input_fingerprint
from mingjing_core.application.agent_tools_dates import event_metadata
from mingjing_core.application.agent_tools_memory import checked_source, source_ref
from mingjing_core.application.agent_tools_policy import CREDENTIAL, refusal
from mingjing_core.application.memory import SECRET
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import hypothetical, mask_quoted
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService

REMIND = re.compile(r"提醒|通知我|叫我|闹钟|remind", re.I)
BENIGN = re.compile(r"(?:别|不要|可别|千万别|请别|勿|切勿)(?:再)?忘(?:记|了)?(?:了)?")
STOP = re.compile(
    r"(?:别|不要|无需|不需要|不用|不必|不想|不愿|不许|不允许|禁止|勿|暂不|不再)"
    r"[^，,。.!！?？；;\n]*(?:提醒|通知|闹钟|叫我|喊我|提示我)"
    r"|(?:取消|关闭|停止|撤销)[^，,。.!！?？；;\n]*(?:提醒|通知|闹钟)"
    r"|\b(?:don['’]?t|do\s+not|never|no\s+need\s+to|not\s+to)\s+(?:remind|notify|set\s+(?:an?\s+)?alarm)",
    re.I,
)
REQUEST = re.compile(
    r"(?:提醒|通知|叫|喊|提示)(?:一下)?我"
    r"|(?:帮我|给我|为我|请你|请|麻烦你|麻烦)[^，,。.!！?？；;\n]*(?:提醒|闹钟)"
    r"|(?:^|[，,。；;\n]|\s)(?:设(?:置|定)?|定|创建|安排|添加)[^，,。.!！?？；;\n]*(?:提醒|闹钟)"
    r"|\b(?:remind|notify)\s+me\b|\bset\s+(?:an?\s+)?alarm\b",
    re.I,
)
REPORTED = re.compile(r"(?:别人|朋友|同事|他|她)(?:说|讲|写)|原话|引用|例句|模板|翻译|这句话|测试(?:句|用例)|演示")


def reminder_intent(text: str, start: int = 0, end: int | None = None) -> str:
    """Negation belongs to the whole original, never an agent-selected substring."""
    end = len(text) if end is None else end
    visible = mask_quoted(text)
    quoted = "".join(original if original != masked else " " for original, masked in zip(text, visible, strict=True))
    if REMIND.search(quoted) or hypothetical(text, 0, len(text)) or REPORTED.search(visible):
        return "ambiguous"
    visible = BENIGN.sub(lambda match: " " * len(match.group()), visible)
    denials = list(STOP.finditer(visible))
    positive = STOP.sub(lambda match: " " * len(match.group()), visible)
    if denials:
        return "ambiguous" if REQUEST.search(positive) else "declined"
    return "confirmed" if REQUEST.search(positive[start:end]) else "absent"


def intent_gate(name: str, source: dict[str, Any], start: int, end: int) -> dict[str, Any] | None:
    intent = reminder_intent(source["content"], start, end)
    if intent == "declined":
        return {"write_status": "stopped", "code": "user_declined_reminders"}
    if intent == "ambiguous":
        return {"write_status": "needs_confirmation", "code": "reminder_intent_ambiguous"}
    if name == "set_reminder" and intent != "confirmed":
        return {"write_status": "needs_confirmation", "code": "explicit_reminder_required"}
    return None


def due_instant(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise EvidenceError("提醒时间必须为带时区的绝对时刻")
    return result.astimezone(UTC)


def schedule_metadata(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
    due: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    zone = service.timezone(ctx)
    local_day = due.astimezone(ZoneInfo(zone)).date()
    # Exact ISO dates require no relative-language lexicon; all relative language
    # is delegated to the injected module parser, anchored to the source instant.
    if local_day.isoformat() in args["quote"]:
        return {
            "said_at": source["at"],
            "owner_timezone": zone,
            "original_expression": local_day.isoformat(),
            "event_at": local_day.isoformat(),
        }, None
    metadata, pending = event_metadata(
        service,
        {"quote": args["quote"], "kind": "event"},
        ctx,
        source,
    )
    if pending:
        return metadata, pending
    event_at = metadata["event_at"]
    event_day = (
        date.fromisoformat(event_at)
        if len(event_at) == 10
        else datetime.fromisoformat(event_at).astimezone(ZoneInfo(zone)).date()
    )
    if event_day != local_day:
        return metadata, {"write_status": "needs_confirmation", "code": "date_conflict"}
    return metadata, None


def validate_fact(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> list[str]:
    ident = args.get("source_fact_id")
    if not ident:
        return []
    if service.repo.is_revoked(ctx.owner, "fact", ident):
        raise EvidenceError("跟进来源事实已撤销")
    facts = service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
    fact = next((row for row in facts if row["id"] == ident), None)
    if fact is None:
        raise ScopeError("跟进来源事实不在当前有效授权范围")
    for ref in fact["source_refs"]:
        source = service.memory.get_source(ctx.owner, ref["message_id"])
        if (
            source["status"] != "active"
            or service.repo.is_revoked(ctx.owner, "message", source["id"])
            or source["revision"] != ref["version"]
            or source.get("thread_id") != ctx.thread_id
        ):
            raise EvidenceError("跟进来源事实已失效")
        service.check_span(ctx, source["id"], ref["start"], ref["end"])
    return [ident]


def followup_due(due: datetime, metadata: dict[str, Any], zone: str) -> datetime:
    """Date-only events get an evening followup; reminders keep their explicit contract."""
    event_at = metadata.get("event_at", "")
    if not isinstance(event_at, str) or len(event_at) != 10:
        return due
    local = due.astimezone(ZoneInfo(zone))
    day = date.fromisoformat(event_at)
    if local.date() == day and 18 <= local.hour < 23:
        return due
    if local.hour >= 23:
        day += timedelta(days=1)
        at = time(8, 30)
    else:
        at = time(20)
    return datetime.combine(day, at, tzinfo=ZoneInfo(zone)).astimezone(UTC)


def persist_schedule(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> dict[str, Any]:
    source, start, end = checked_source(service, args, ctx)
    refused = refusal(source, args["quote"], start, end)
    if refused:
        return refused
    if hypothetical(source["content"], start, end):
        return {"write_status": "rejected", "code": "hypothetical"}
    title = args.get("text", args.get("topic", ""))
    if any(SECRET.search(value) or CREDENTIAL.search(value) for value in (title, args.get("reason", ""))):
        return {"write_status": "rejected", "code": "credential"}
    pending_intent = intent_gate(name, source, start, end)
    if pending_intent:
        return pending_intent
    settings = service.repo.assert_scope(ctx.owner, ctx.subject)["settings"]
    if name == "schedule_followup" and settings.get("proactive_followups_enabled", True) is not True:
        return {"write_status": "stopped", "code": "proactive_disabled"}
    due = due_instant(args["due_at"])
    metadata, pending = schedule_metadata(service, args, ctx, source, due)
    if pending:
        return pending
    if name == "schedule_followup":
        due = followup_due(due, metadata, service.timezone(ctx))
    if due <= service.clock.now():
        raise EvidenceError("提醒时间必须在当前时刻之后")
    if name == "set_reminder":
        local_time = due.astimezone(ZoneInfo(service.timezone(ctx))).strftime("%H:%M")
        if args["text"] not in args["quote"] or local_time not in args["quote"]:
            return {"write_status": "needs_confirmation", "code": "reminder_text_or_time_unconfirmed"}
    facts = validate_fact(service, args, ctx)
    kind = "reminder" if name == "set_reminder" else "followup"
    ident = kind + "_" + fingerprint([ctx.owner, ctx.operation_id])[:32]
    return write_schedule(service, args, ctx, source, start, end, metadata, due, facts, kind, ident)


def write_schedule(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
    start: int,
    end: int,
    metadata: dict[str, Any],
    due: datetime,
    facts: list[str],
    kind: str,
    ident: str,
) -> dict[str, Any]:
    title = args.get("text", args.get("topic", ""))
    row = service.repo.put(
        ctx.owner,
        kind,
        ident,
        dict(
            metadata,
            topic=title,
            text=title,
            reason=args.get("reason", ""),
            due_at=due.isoformat(),
            due_ms=int(due.timestamp() * 1000),
            source_fact_id=args.get("source_fact_id"),
            fact_ids=facts,
            source_ids=[source["id"]],
            source_refs=[source_ref(source, start, end)],
            thread_id=ctx.thread_id,
            status="active",
            channel="feishu",
            explicit=kind == "reminder",
        ),
        subject=ctx.subject,
        expected_revision=0,
        operation_id=ctx.operation_id + ":" + kind,
    )
    return {"write_status": "saved", "id": row["id"], "kind": kind, "revision": row["revision"]}


def execute_schedule(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    with service.repo.transaction(ctx.owner) as connection:
        service.authority(connection, ctx)
        if (
            name != ctx.name
            or name not in {"schedule_followup", "set_reminder"}
            or tool_input_fingerprint(name, args, ctx.source_versions) != ctx.input_fp
            or ctx.crisis
        ):
            raise ScopeError("当前模式不可使用跟进工具")
        if ctx.private:
            return ToolResult(ok=False, data={"code": "incognito"}, summary="无痕模式未写入长期提醒")
        source, start, end = checked_source(service, args, ctx)
        service.check_span(ctx, source["id"], start, end)
        validate_fact(service, args, ctx)
        receipt = service.repo.mutation_request(
            ctx.owner,
            "agent_" + name,
            ctx.operation_id,
            args,
            partial(persist_schedule, service, name, args, ctx),
        )
        if receipt.get("id"):
            row = service.repo.get(ctx.owner, receipt["kind"], receipt["id"], include_deleted=True)
            if row["status"] != "active":
                raise EvidenceError("提醒记录已撤销")
        return ToolResult(
            ok=receipt["write_status"] == "saved", receipt=receipt, summary="提醒记录状态：" + receipt["write_status"]
        )

"""Offline calendar facts and authorized repository projections for read tools."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.application.agent_tools_projection import project_result, sources_active
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.tokenize import tokenize
from mingjing_core.timekit.almanac import almanac
from mingjing_core.timekit.calendar_cn import day_status
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService


def day_data(day: date, zone: str) -> dict[str, Any]:
    at = datetime.combine(day, time(12), ZoneInfo(zone))
    return dict(almanac(at, zone).to_dict(), day_status=asdict(day_status(day)))


def time_context(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    zone = service.timezone(ctx)
    at = (ctx.at or service.clock.now()).astimezone(ZoneInfo(zone))
    if args["date"]:
        day = date.fromisoformat(args["date"])
        local_time = time.fromisoformat(args["time"]) if args["time"] else time(12)
        if local_time.tzinfo is not None:
            raise EvidenceError("时间参数使用人物当地时间")
        at = datetime.combine(day, local_time, ZoneInfo(zone))
    elif args["time"]:
        raise EvidenceError("指定时间需要同时指定绝对日期")
    return dict(
        almanac(at, zone).to_dict(),
        at=at.isoformat(),
        timezone=zone,
        day_status=asdict(day_status(at.date())),
    )


def event_day(row: dict[str, Any], zone: str) -> date | None:
    value = row.get("event_at") or row.get("at") or row.get("created_at")
    if isinstance(value, str) and len(value) == 10:
        return date.fromisoformat(value)
    instant = history_instant(value)
    return instant.astimezone(ZoneInfo(zone)).date() if instant else None


def calendar_lookup(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    start = date.fromisoformat(args["start_date"])
    end = date.fromisoformat(args["end_date"] or args["start_date"])
    if not 0 <= (end - start).days <= 365:
        raise EvidenceError("历法区间需要有序且不超过366日")
    zone = service.timezone(ctx)
    events = [
        row
        for row in service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
        if row.get("event_at") and sources_active(service, row, ctx)
    ]
    days = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        data = day_data(day, zone)
        data["events"] = [
            {
                "id": row["id"],
                "summary": row.get("summary", row["content"]),
                "event_at": row["event_at"],
            }
            for row in events
            if event_day(row, zone) == day
        ]
        days.append(data)
    return {"timezone": zone, "days": days}


def memory_search(service: AgentToolsService, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    zone = service.timezone(ctx)
    since = date.fromisoformat(args["since"]) if args["since"] else None
    until = date.fromisoformat(args["until"]) if args["until"] else None
    if since and until and until < since:
        raise EvidenceError("检索时间区间顺序无效")
    facts = [
        row
        for row in service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
        if sources_active(service, row, ctx)
    ]
    valid = {row["id"] for row in facts}
    items = []
    for kind in dict.fromkeys(args["kinds"]):
        rows = service.repo.search(ctx.owner, ctx.subject, tokenize(args["query"]), [kind], limit=100)
        for row in rows:
            if kind == "fact" and row["id"] not in valid:
                continue
            row = project_result(service, row, kind, ctx, facts)
            if row is None:
                continue
            day = event_day(row, zone)
            if (since and (day is None or day < since)) or (until and (day is None or day > until)):
                continue
            items.append(dict(row, entity_kind=kind))
    items.sort(key=lambda row: (-row.get("search_rank", 0), row["id"]))
    return {
        "items": items[: args["limit"]],
        "candidate_limit_per_kind": 100,
        "date_basis": "event_at_or_source_time",
    }


def execute_read(
    service: AgentToolsService,
    name: str,
    args: dict[str, Any],
    ctx: ToolContext,
) -> ToolResult:
    if name == "time_context":
        data = time_context(service, args, ctx)
    elif name == "calendar_lookup":
        data = calendar_lookup(service, args, ctx)
    elif name == "memory_search":
        data = memory_search(service, args, ctx)
    elif name == "profile_get":
        data = profile_get(service, ctx)
    else:
        raise EvidenceError("未注册的读取工具")
    return ToolResult(ok=True, data=data, summary="工具查询已完成")


def profile_get(service: AgentToolsService, ctx: ToolContext) -> dict[str, Any]:
    facts = [
        row
        for row in service.memory.facts(ctx.owner, ctx.subject, list(ctx.case_ids))
        if sources_active(service, row, ctx)
    ]
    profile, conflicts = {}, set()
    for row in facts:
        field = row.get("field")
        if not field:
            continue
        if field in profile and profile[field] != row.get("value"):
            conflicts.add(field)
        profile[field] = row.get("value")
    for field in conflicts:
        profile.pop(field, None)
    return {"profile": profile, "conflicts": sorted(conflicts), "facts": facts}

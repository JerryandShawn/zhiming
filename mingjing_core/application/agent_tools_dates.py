"""U4 integration boundary; relative-date language belongs to the timekit module."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext


def valid_event_at(value: str) -> str:
    if len(value) == 10:
        return date.fromisoformat(value).isoformat()
    instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise EvidenceError("事件时刻必须带时区")
    return instant.astimezone(UTC).isoformat()


def event_metadata(
    service: AgentToolsService,
    args: dict[str, Any],
    ctx: ToolContext,
    source: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    said_at = history_instant(source.get("at"))
    if said_at is None:
        raise EvidenceError("来源时间无法确认")
    zone = service.timezone(ctx)
    ZoneInfo(zone)
    metadata = {"said_at": said_at.astimezone(UTC).isoformat(), "owner_timezone": zone}
    claimed = args.get("date_expression") or args.get("event_at") or args["kind"] == "event"
    if not claimed:
        # A goal or preference can contain a vague word such as 最近 without
        # claiming a calendar event. Preserve the source instant, not an
        # invented event_at, and leave date confirmation to actual event writes.
        return metadata, None
    if service.relative_parser is None:
        if claimed:
            return metadata, {
                "write_status": "needs_confirmation",
                "code": "date_parser_unavailable",
            }
        return metadata, None
    result = service.relative_parser.resolve(args["quote"], said_at=said_at, timezone=zone)
    if result.status == "needs_confirmation":
        return metadata, {
            "write_status": "needs_confirmation",
            "code": "date_ambiguous",
        }
    if result.status == "not_date":
        if claimed:
            return metadata, {
                "write_status": "needs_confirmation",
                "code": "date_not_confirmed",
            }
        return metadata, None
    if result.status != "resolved" or not result.event_at or not result.expression:
        raise EvidenceError("日期模块返回结果无效")
    if result.expression not in args["quote"]:
        raise EvidenceError("日期表达必须逐字来自原话")
    event_at = valid_event_at(result.event_at)
    if args.get("event_at") and valid_event_at(args["event_at"]) != event_at:
        return metadata, {"write_status": "needs_confirmation", "code": "date_conflict"}
    if args.get("date_expression") and args["date_expression"] != result.expression:
        return metadata, {
            "write_status": "needs_confirmation",
            "code": "date_expression_conflict",
        }
    return dict(metadata, event_at=event_at, original_expression=result.expression), None

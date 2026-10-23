"""Validate and encode public SSE events from one frozen v1 source."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from mingjing_core.agent import event_contracts as c
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import Clock, get_clock

EVENTS: dict[str, type[c.EventData]] = {
    "started": c.Started,
    "status": c.Status,
    "tool_call": c.ToolCallEvent,
    "tool_result": c.ToolResultEvent,
    "text_delta": c.TextDelta,
    "text_reset": c.TextReset,
    "memory_receipt": c.MemoryReceipt,
    "ask_user": c.AskUserEvent,
    "present_options": c.PresentOptionsEvent,
    "review": c.ReviewEvent,
    "final": c.Final,
    "error": c.Error,
}


def validate_event(kind: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(kind, str) or kind not in EVENTS:
        raise EvidenceError("未知公开事件类型")
    try:
        # Keep required nullable asked/options in nested core4 envelopes.
        return EVENTS[kind].model_validate(data).model_dump(by_alias=True, exclude_unset=True)
    except (ValidationError, TypeError, ValueError):
        raise EvidenceError("事件格式无效") from None


def make_event(
    kind: str,
    run_id: str,
    seq: int,
    payload: dict[str, Any],
    *,
    clock: Clock | None = None,
) -> dict[str, Any]:
    if set(payload).intersection({"v", "run_id", "seq", "ts"}):
        raise EvidenceError("事件正文不能覆盖公共身份")
    stamp = (clock or get_clock()).now()
    if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
        raise EvidenceError("事件时钟必须带时区")
    data = dict(payload, v=1, run_id=run_id, seq=seq, ts=stamp.astimezone(ZoneInfo("Asia/Shanghai")).isoformat())
    return {"type": kind, "data": validate_event(kind, data)}


def encode_sse(event: dict[str, Any]) -> str:
    if set(event) != {"type", "data"}:
        raise EvidenceError("事件封装无效")
    kind = event["type"]
    data = validate_event(kind, event["data"])
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return f"id: {data['seq']}\nevent: {kind}\ndata: {encoded}\n\n"


def heartbeat() -> str:
    return ": ping\n\n"


def event_schema() -> dict[str, Any]:
    definitions: dict[str, Any] = {}
    choices = []
    for kind, model in EVENTS.items():
        child = deepcopy(model.model_json_schema(by_alias=True, ref_template="#/$defs/{model}"))
        definitions.update(child.pop("$defs", {}))
        definitions[model.__name__] = child
        choices.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "data"],
                "properties": {"type": {"const": kind}, "data": {"$ref": "#/$defs/" + model.__name__}},
            }
        )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:mingjing:events:v1",
        "title": "明镜公开事件契约v1",
        "oneOf": choices,
        "$defs": definitions,
    }


def envelope_schema() -> dict[str, Any]:
    result = c.EnvelopeV1.model_json_schema(by_alias=True)
    return dict(result, **{"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "urn:mingjing:core4:v1"})

"""One canonical CaseUpdate payload for the real writer and private proof verifier."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_tools_memory import source_ref
from mingjing_core.domain.contracts import EvidenceError


def case_update_payload(
    before: dict[str, Any], args: dict[str, Any], source: dict[str, Any], start: int, end: int
) -> dict[str, Any]:
    changes = {key: value for key, value in args["changes"].items() if value is not None}
    if not changes:
        raise EvidenceError("事项修改不能为空")
    for field in ("title", "goal"):
        if field in changes and changes[field] not in args["quote"]:
            raise EvidenceError("事项标题和目标必须逐字来自用户原话")
    payload = {key: value for key, value in changes.items() if key in {"title", "status"}}
    if "goal" in changes:
        payload["state"] = dict(before.get("state", {}), goal=changes["goal"])
    payload["source_refs"] = list(before.get("source_refs", [])) + [source_ref(source, start, end)]
    fields = dict(before.get("field_source_refs", {}))
    for field in ("title", "goal"):
        fields.setdefault(field, list(before.get("source_refs", [])))
        if field in changes:
            offset = source["content"].index(changes[field], start, end)
            fields[field] = [source_ref(source, offset, offset + len(changes[field]))]
    payload["field_source_refs"] = fields
    return payload

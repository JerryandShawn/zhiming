"""Project tool reads through the same selected-case and revocation boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.threads import project_sources

if TYPE_CHECKING:
    from mingjing_core.application.agent_tools import AgentToolsService
    from mingjing_core.application.agent_tools_contracts import ToolContext


def sources_active(service: AgentToolsService, row: dict[str, Any], ctx: ToolContext, kind: str = "fact") -> bool:
    if row.get("subject_id") != ctx.subject or row.get("status") != "active":
        return False
    if row.get("case_id") is not None and row["case_id"] not in ctx.case_ids:
        return False
    refs, ids = row.get("source_refs", []), row.get("source_ids", [])
    if not isinstance(refs, list) or not isinstance(ids, list):
        return False
    if kind != "message" and not refs and not ids:
        return False
    if any(not isinstance(ref, dict) or not isinstance(ref.get("message_id"), str) for ref in refs):
        return False
    if any(not isinstance(ident, str) for ident in ids):
        return False
    if kind == "message" and (
        row.get("thread_id") != "life:" + ctx.subject or row.get("role") not in {"user", "assistant"}
    ):
        return False
    for ident in set(ids) | {ref["message_id"] for ref in refs}:
        if not _source_active(service, ident, refs, ctx, kind):
            return False
    return True


def _source_active(
    service: AgentToolsService, ident: str, refs: list[dict[str, Any]], ctx: ToolContext, kind: str
) -> bool:
    try:
        source = service.memory.get_source(ctx.owner, ident)
        if source["subject_id"] != ctx.subject or source["status"] != "active":
            return False
        if source.get("thread_id") != "life:" + ctx.subject or service.repo.is_revoked(ctx.owner, "message", ident):
            return False
        if kind == "fact" and source.get("role") != "user":
            return False
        if kind != "fact" and not set(source.get("case_ids", [])) <= set(ctx.case_ids):
            return False
        linked = [ref for ref in refs if ref["message_id"] == ident]
        if any(ref.get("version", source["revision"]) != source["revision"] for ref in linked):
            return False
        for ref in linked or [{}]:
            start, end = ref.get("start", 0), ref.get("end", len(source["content"]))
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["content"]):
                return False
            if "quote" in ref and source["content"][start:end] != ref["quote"]:
                return False
            service.check_span(ctx, ident, start, end)
    except (EvidenceError, ScopeError, KeyError, TypeError):
        return False
    return True


def project_result(
    service: AgentToolsService, row: dict[str, Any], kind: str, ctx: ToolContext, facts: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not sources_active(service, row, ctx, kind):
        return None
    groups = (row.get("fact_ids", []), row.get("used_fact_ids", []))
    if any(not isinstance(group, list) or any(not isinstance(ident, str) for ident in group) for group in groups):
        return None
    used = groups[0] + groups[1]
    if row.get("source_fact_id"):
        used.append(row["source_fact_id"])
    if not set(used) <= {fact["id"] for fact in facts}:
        return None
    if kind == "message":
        original = service.memory.get_source(ctx.owner, row["id"])
        if original["status"] != "active" or service.repo.is_revoked(ctx.owner, "message", row["id"]):
            return None
        rows = project_sources(service.memory, ctx.owner, [original], facts, set(ctx.case_ids))
        if not rows:
            return None
        row = rows[0]
        fields = ("id", "role", "content", "channel", "at", "revision", "created_at", "status")
    else:
        fields = (
            "id",
            "content",
            "summary",
            "inferred",
            "assertion_status",
            "source_ids",
            "source_refs",
            "channel",
            "event_at",
            "said_at",
            "revision",
            "created_at",
            "status",
            "field",
            "value",
        )
    return {key: row[key] for key in fields if key in row} | {
        "entity_kind": kind,
        "search_rank": row.get("search_rank", 0),
    }

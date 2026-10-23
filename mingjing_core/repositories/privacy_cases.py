"""Erase case fields derived from a withdrawn span while preserving the case ID."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError

if TYPE_CHECKING:
    from mingjing_core.repositories.postgres import PostgresRepository


def _support(
    repo: PostgresRepository, owner: str, ref: dict[str, Any], text: str, spans: dict[str | None, list[dict[str, Any]]]
) -> str:
    ident = ref.get("message_id")
    if not isinstance(ident, str):
        return "none"
    try:
        source = repo.get(owner, "message", ident)
    except (ScopeError, EvidenceError):
        return "withdrawn"
    content = source.get("content", "")
    if source["revision"] != ref.get("version", source["revision"]):
        return "withdrawn"
    if not text:
        return "none"
    left, right = ref.get("start", 0), ref.get("end", len(content))
    if type(left) is not int or type(right) is not int or not 0 <= left < right <= len(content):
        return "withdrawn"
    matches = []
    start = content.find(text, left, right)
    while start >= 0:
        matches.append((start, start + len(text)))
        start = content.find(text, start + 1, right)
    if not matches:
        return "none"
    for item in spans.get(ident, []):
        a, b = item.get("start"), item.get("end")
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(content):
            return "withdrawn"
        if any(max(start, a) < min(end, b) for start, end in matches):
            return "withdrawn"
    return "valid"


def _withdrawn_field(
    repo: PostgresRepository,
    owner: str,
    row: dict[str, Any],
    field: str,
    value: str,
    spans: dict[str | None, list[dict[str, Any]]],
) -> bool:
    linked = row.get("field_source_refs", {}).get(field, row.get("source_refs", []))
    states = {_support(repo, owner, ref, value, spans) for ref in linked}
    return "withdrawn" in states and "valid" not in states


def _safe_field_refs(
    repo: PostgresRepository,
    owner: str,
    row: dict[str, Any],
    field: str,
    value: str,
    spans: dict[str | None, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    refs = row.get("field_source_refs", {}).get(field, row.get("source_refs", []))
    result = []
    for ref in refs:
        if _support(repo, owner, ref, value, spans) != "valid":
            continue
        source = repo.get(owner, "message", ref["message_id"])
        start = source["content"].find(value, ref.get("start", 0))
        result.append(
            {
                "message_id": source["id"],
                "version": source["revision"],
                "start": start,
                "end": start + len(value),
                "quote": value,
            }
        )
    return result


def redact_case_fields(
    repo: PostgresRepository, owner: str, spans: dict[str | None, list[dict[str, Any]]], partial_sources: set[str]
) -> None:
    if not partial_sources:
        return
    for row in repo.list(owner, "case"):
        linked = {ref.get("message_id") for ref in row.get("source_refs", [])}
        if not linked.intersection(partial_sources):
            continue
        changes: dict[str, Any] = {}
        state = row.get("state", {})
        if _withdrawn_field(repo, owner, row, "goal", state.get("goal", ""), spans):
            changes["state"] = dict(state, goal="")
        if _withdrawn_field(repo, owner, row, "title", row.get("title", ""), spans):
            changes["title"] = "已撤销的事项"
        field_refs = {
            name: [ref for ref in refs if ref.get("message_id") not in partial_sources]
            for name, refs in row.get("field_source_refs", {}).items()
        }
        for field, value in (("title", row.get("title", "")), ("goal", state.get("goal", ""))):
            erased = field in changes or field == "goal" and "state" in changes
            field_refs[field] = [] if erased else _safe_field_refs(repo, owner, row, field, value, spans)
        retained = [ref for ref in row.get("source_refs", []) if ref.get("message_id") not in partial_sources]
        for refs in field_refs.values():
            retained.extend(ref for ref in refs if ref not in retained)
        changes.update(source_refs=retained, field_source_refs=field_refs)
        repo.update(owner, "case", row["id"], changes, expected_revision=row["revision"])

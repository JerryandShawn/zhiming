"""Read bounded derived context only while its original lineage remains usable."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError

from .context_types import ContextInputError

if TYPE_CHECKING:
    from .context_sources import BoundedSources


KINDS = (
    "case",
    "feedback",
    "note",
    "episode",
    "thread_summary",
    "knowledge_gap",
    "followup",
    "reminder",
)


def _linked(row: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str]]:
    refs = row.get("source_refs", [])
    sources = row.get("source_ids", [])
    if not isinstance(refs, list) or not isinstance(sources, list):
        raise ContextInputError("context_lineage_invalid")
    if any(not isinstance(ref, dict) or not isinstance(ref.get("message_id"), str) for ref in refs):
        raise ContextInputError("context_lineage_invalid")
    if any(not isinstance(ident, str) for ident in sources):
        raise ContextInputError("context_lineage_invalid")
    return refs, set(sources) | {ref["message_id"] for ref in refs}


def _fact_ids(row: dict[str, Any]) -> set[str]:
    values = (row.get("fact_ids", []), row.get("used_fact_ids", []))
    if any(not isinstance(value, list) or any(not isinstance(item, str) for item in value) for value in values):
        raise ContextInputError("context_lineage_invalid")
    ident = row.get("source_fact_id")
    if ident is not None and not isinstance(ident, str):
        raise ContextInputError("context_lineage_invalid")
    return set(values[0]) | set(values[1]) | ({ident} if ident else set())


def _valid(
    sources: BoundedSources,
    owner: str,
    subject: str,
    row: dict[str, Any],
    facts: set[str],
) -> bool:
    refs, linked = _linked(row)
    if len(linked) > sources.policy.source_ref_limit:
        raise ContextInputError("context_source_catalog_overflow")
    if row.get("thread_id", "life:" + subject) != "life:" + subject:
        return False
    used = _fact_ids(row)
    if not used <= facts:
        return False
    if not linked and not used:
        # Only an explicitly selected, source-free case title may be shown.
        state = row.get("state", {})
        if not isinstance(state, dict):
            raise ContextInputError("context_lineage_invalid")
        return row["entity_kind"] == "case" and not state.get("goal")
    for ident in linked:
        try:
            original = sources._source(owner, ident)
        except (ScopeError, EvidenceError):
            return False
        if original["subject_id"] != subject or original["status"] != "active":
            return False
        if original.get("thread_id") != "life:" + subject or ident in sources.deleted or sources.spans.get(ident):
            return False
        if original.get("redacted") or sources.boundary is None or sources._key(original) > sources.boundary:
            return False
        if any(
            ref.get("version", original["revision"]) != original["revision"]
            for ref in refs
            if ref["message_id"] == ident
        ):
            return False
    return True


def read_entities(
    sources: BoundedSources,
    owner: str,
    subject: str,
    cases: tuple[str, ...],
    facts: list[dict[str, Any]],
) -> dict[str, tuple[dict[str, Any], ...]]:
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    valid_facts = {fact["id"] for fact in facts}
    total_links = 0
    for kind in KINDS:
        rows = sources.repo.list(
            owner,
            kind,
            subject=subject,
            case_ids=list(cases),
            limit=sources.policy.extra_entity_limit + 1,
        )
        if len(rows) > sources.policy.extra_entity_limit:
            raise ContextInputError("context_entity_catalog_overflow")
        selected = []
        for value in rows:
            row = dict(value, entity_kind=kind)
            if row["status"] not in {"active", "open", "pending"}:
                continue
            if kind == "case" and row["id"] not in cases or kind == "feedback" and row.get("case_id") not in cases:
                continue
            _, linked = _linked(row)
            total_links += len(linked)
            if total_links > sources.policy.source_ref_limit:
                raise ContextInputError("context_source_catalog_overflow")
            if _valid(sources, owner, subject, row, valid_facts):
                selected.append(row)
        result[kind] = tuple(selected)
    return result

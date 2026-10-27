"""Source anchors are mandatory even when a caller claims prior authorization."""

import re

from mingjing_core.memory.policy import hypothetical, mask_quoted

from .consent_text import has_storage_optout
from .contracts import MemoryFact, MemoryScope, MemorySnapshot, SourceAnchor

_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}|(?:密码|口令|密钥|api[_ -]?key)\s*[:：=]", re.I)


class MemoryGuardError(ValueError):
    """Machine reason only, never private text."""


def authorize_fact(
    fact: MemoryFact, snapshot: MemorySnapshot, scope: MemoryScope, *, allow_retired: bool = False
) -> None:
    if snapshot.scope != scope or (fact.owner_id, fact.subject_id) != (scope.owner_id, scope.subject_id):
        raise MemoryGuardError("scope_mismatch")
    if not fact.source_valid or (not allow_retired and fact.status != "active"):
        raise MemoryGuardError("fact_unavailable")
    if not fact.source_ids or len(set(fact.source_ids)) != len(fact.source_ids):
        raise MemoryGuardError("source_required")
    if set(fact.source_ids) != {anchor.source_id for anchor in fact.anchors}:
        raise MemoryGuardError("source_anchor_required")
    for anchor in fact.anchors:
        _authorize_anchor(fact, snapshot, scope, anchor)
    primary = snapshot.source(fact.source_ids[0])
    if primary is None or primary.at != fact.said_at:
        raise MemoryGuardError("said_at_must_match_source")
    if fact.recorded_at < fact.said_at:
        raise MemoryGuardError("recorded_before_source")


def _authorize_anchor(fact: MemoryFact, snapshot: MemorySnapshot, scope: MemoryScope, anchor: SourceAnchor) -> None:
    source = snapshot.source(anchor.source_id)
    if source is None or (source.owner_id, source.subject_id) != (scope.owner_id, scope.subject_id):
        raise MemoryGuardError("source_scope_mismatch")
    if not source.active or source.revoked or source.incognito or source.optout:
        raise MemoryGuardError("source_unavailable")
    if source.revision != anchor.revision:
        raise MemoryGuardError("source_revision_changed")
    if not 0 <= anchor.start < anchor.end <= len(source.text) or source.text[anchor.start : anchor.end] != anchor.quote:
        raise MemoryGuardError("source_quote_mismatch")
    if has_storage_optout(source.text) or _SECRET.search(source.text):
        raise MemoryGuardError("source_storage_forbidden")
    if fact.origin == "user" and (source.role != "user" or source.origin != "current_user"):
        raise MemoryGuardError("user_source_required")
    if fact.origin == "user" and (
        hypothetical(source.text, anchor.start, anchor.end)
        or not mask_quoted(source.text)[anchor.start : anchor.end].strip()
    ):
        raise MemoryGuardError("user_assertion_required")
    if fact.origin != "user" and (
        fact.origin != "assistant_claim" or fact.kind not in {"note", "assistant_claim"} or source.role != "assistant"
    ):
        raise MemoryGuardError("assistant_cannot_be_user_fact")

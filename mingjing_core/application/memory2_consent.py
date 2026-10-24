"""Memory category grants stay tied to the original and the user's confirmation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import has_optout
from mingjing_core.memory.private import is_private

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


def consent_live(memory: MemoryService, owner: str, subject: str, consent: dict[str, Any]) -> bool:
    if consent.get("status") != "active" or consent.get("subject_id") != subject:
        return False
    if memory.repo.is_revoked(owner, "consent", consent["id"]):
        return False
    spans = [row["metadata"] for row in memory.repo.revocations(owner) if row["kind"] == "source_span"]
    for prefix in ("source", "approval"):
        ident = consent.get("message_id" if prefix == "source" else "approval_message_id")
        try:
            original = memory.get_source(owner, ident)
        except (ScopeError, EvidenceError):
            return False
        start = consent.get("scope_start" if prefix == "source" else "approval_start")
        end = consent.get("scope_end" if prefix == "source" else "approval_end")
        version = consent.get("source_revision" if prefix == "source" else "approval_revision")
        policy = original.get("policy", {})
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(original.get("content", ""))
            or original["subject_id"] != subject
            or original["revision"] != version
            or original["status"] != "active"
            or original.get("role") != "user"
            or is_private(original)
            or original.get("thread_id") != "life:" + subject
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or has_optout(original["content"])
            or memory.repo.is_revoked(owner, "message", ident)
        ):
            return False
        if any(span.get("message_id") == ident and max(start, span["start"]) < min(end, span["end"]) for span in spans):
            return False
    return True


def categories_granted(memory: MemoryService, owner: str, subject: str, categories: tuple[str, ...]) -> bool:
    settings = memory.repo.assert_scope(owner, subject)["settings"]
    granted = settings.get("auto_save_categories", [])
    proofs = settings.get("memory_category_authorizations", {})
    if (
        not isinstance(granted, list)
        or any(not isinstance(item, str) for item in granted)
        or not isinstance(proofs, dict)
        or not set(categories) <= set(granted)
    ):
        return False
    for category in categories:
        ident = proofs.get(category)
        if category not in proofs:
            # Existing owner-configured grants predate proposal evidence records.
            continue
        if not isinstance(ident, str) or not ident:
            return False
        try:
            proof = memory.repo.get(owner, "consent", ident)
        except (ScopeError, EvidenceError):
            return False
        if category not in proof.get("categories", []) or not consent_live(memory, owner, subject, proof):
            return False
    return True


def category_authority_refs(
    memory: MemoryService, owner: str, subject: str, categories: tuple[str, ...]
) -> tuple[list[dict[str, Any]], list[str]]:
    settings = memory.repo.assert_scope(owner, subject)["settings"]
    proofs = settings.get("memory_category_authorizations", {})
    refs, ids = [], []
    for category in categories:
        ident = proofs.get(category)
        if ident is None or ident in ids:
            continue
        proof = memory.repo.get(owner, "consent", ident)
        if not consent_live(memory, owner, subject, proof):
            raise EvidenceError("记忆分类授权已经失效")
        ids.append(ident)
        for prefix in ("source", "approval"):
            message_id = proof["message_id" if prefix == "source" else "approval_message_id"]
            original = memory.get_source(owner, message_id)
            start = proof["scope_start" if prefix == "source" else "approval_start"]
            end = proof["scope_end" if prefix == "source" else "approval_end"]
            ref = {
                "message_id": message_id,
                "version": original["revision"],
                "start": start,
                "end": end,
                "quote": original["content"][start:end],
            }
            if ref not in refs:
                refs.append(ref)
    return refs, ids

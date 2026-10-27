"""Memory category grants stay tied to the original and the user's confirmation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import has_optout
from mingjing_core.memory.private import is_private
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


def consent_live(
    memory: MemoryService,
    owner: str,
    subject: str,
    consent: dict[str, Any],
    *,
    ledger: list[dict] | None = None,
    originals: dict | None = None,
) -> bool:
    if consent.get("status") != "active" or consent.get("subject_id") != subject:
        return False
    ledger = memory.repo.revocations(owner) if ledger is None else ledger
    revoked = {(row["kind"], row["entity_id"]) for row in ledger}
    if ("consent", consent["id"]) in revoked:
        return False
    spans = [row["metadata"] for row in ledger if row["kind"] == "source_span"]
    originals = {} if originals is None else originals
    for prefix in ("source", "approval"):
        ident = consent.get("message_id" if prefix == "source" else "approval_message_id")
        try:
            if ident not in originals:
                originals[ident] = memory.get_source(owner, ident)
            original = originals[ident]
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
            or not unchanged_quote(memory, owner, consent, prefix, original, start, end, version)
            or original["status"] != "active"
            or original.get("role") != "user"
            or is_private(original)
            or original.get("thread_id") != "life:" + subject
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or has_optout(original["content"])
            or ("message", ident) in revoked
        ):
            return False
        if any(span.get("message_id") == ident and max(start, span["start"]) < min(end, span["end"]) for span in spans):
            return False
    return True


def unchanged_quote(
    memory: MemoryService, owner: str, consent: dict, prefix: str, original: dict, start: int, end: int, version: int
) -> bool:
    """Compare the authorized interval; a revision bump elsewhere is not revocation."""
    expected = consent.get(prefix + "_quote_hash")
    if not expected:
        try:
            proposal = memory.repo.get(owner, "proposal", consent["proposal_id"])
        except (KeyError, EvidenceError, ScopeError):
            return False
        ref = next(
            (
                ref
                for ref in proposal.get("source_refs", [])
                if ref.get("message_id") == original["id"]
                and ref.get("start") == start
                and ref.get("end") == end
                and ref.get("version") == version
            ),
            None,
        )
        if ref is None or not isinstance(ref.get("quote"), str):
            return False
        expected = fingerprint([ref["quote"]])
    return expected == fingerprint([original["content"][start:end]])


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

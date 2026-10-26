"""Project P5 facts only while their exact consent records remain live."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_consent import consent_live
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.dependencies import entity_dependency
from mingjing_core.repositories.postgres import fingerprint

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mingjing_core.application.memory import MemoryService


def fact_consent_ids(fact: dict[str, Any]) -> tuple[str, ...]:
    ids = fact.get("category_consent_ids", [])
    if not isinstance(ids, list) or len(ids) > 16 or any(not isinstance(ident, str) or not ident for ident in ids):
        raise EvidenceError("记忆授权引用结构无效")
    if "approval_consent_id" in fact:
        approval = fact["approval_consent_id"]
        if not isinstance(approval, str) or not approval:
            raise EvidenceError("记忆确认授权引用无效")
        ids = [*ids, approval]
    return tuple(dict.fromkeys(ids))


def fact_consents_live(memory: MemoryService, owner: str, subject: str, fact: dict[str, Any]) -> bool:
    """No P5 reference means the existing v3 projection remains unchanged."""
    try:
        return all(
            consent_live(memory, owner, subject, memory.repo.get(owner, "consent", ident))
            for ident in fact_consent_ids(fact)
        )
    except (EvidenceError, ScopeError, KeyError, TypeError, ValueError):
        return False


def consent_verifier(memory: MemoryService, owner: str, subject: str):
    """Caller holds the owner transaction; no memo survives this facts() call."""
    ledger, originals, proofs = None, {}, {}

    def verify(fact: dict) -> bool:
        nonlocal ledger
        try:
            ids = fact_consent_ids(fact)
            if ids and ledger is None:
                ledger = memory.repo.revocations(owner)
            for ident in ids:
                if ident not in proofs:
                    try:
                        proof = memory.repo.get(owner, "consent", ident)
                        proofs[ident] = consent_live(memory, owner, subject, proof, ledger=ledger, originals=originals)
                    except (EvidenceError, ScopeError):
                        proofs[ident] = False
                    if not proofs[ident]:
                        inactive_notice(memory, owner, subject, ident)
                if not proofs[ident]:
                    return False
            return True
        except (EvidenceError, ScopeError, KeyError, TypeError, ValueError):
            return False

    return verify


def inactive_notice(memory: MemoryService, owner: str, subject: str, consent_id: str) -> None:
    ident = "memory_authority_notice_" + fingerprint([owner, subject, consent_id])[:24]
    try:
        memory.repo.get(owner, "knowledge_gap", ident, include_deleted=True)
        return
    except ScopeError:
        pass
    if memory.repo.is_revoked(owner, "knowledge_gap", ident):
        return
    memory.repo.put(
        owner,
        "knowledge_gap",
        ident,
        {
            "kind": "memory_authority_notice",
            "summary": "一项记忆保存授权已失效，相关内容暂不用于回答。",
            "consent_ids": [consent_id],
            "inferred": True,
        },
        subject=subject,
        expected_revision=0,
    )


def fact_consent_versions(
    memory: MemoryService, owner: str, subject: str, facts: Iterable[dict[str, Any]]
) -> dict[str, int]:
    versions = {}
    for fact in facts:
        for ident in fact_consent_ids(fact):
            key = entity_dependency("consent", ident)
            if key in versions:
                continue
            proof = memory.repo.get(owner, "consent", ident)
            if not consent_live(memory, owner, subject, proof):
                raise EvidenceError("记忆授权在构建上下文时已失效")
            versions[key] = proof["revision"]
    return versions

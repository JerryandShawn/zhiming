"""Project P5 facts only while their exact consent records remain live."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_consent import consent_live
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.dependencies import entity_dependency

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

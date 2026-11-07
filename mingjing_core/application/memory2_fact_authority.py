"""Revalidate stored user facts before memory transformations and cached effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_policy import SENSITIVITIES, sensitivity, sensitivity_categories
from mingjing_core.application.memory import explicit_save_authorization
from mingjing_core.application.memory2_consent import categories_granted, consent_live
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.policy import authorization_clause, has_optout
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from datetime import datetime

    from mingjing_core.application.memory import MemoryService


def authorized_fact(
    memory: MemoryService, owner: str, subject: str, ident: str, *, statuses: frozenset[str]
) -> dict[str, Any]:
    fact = memory.repo.get(owner, "fact", ident, include_deleted=True)
    if fact["subject_id"] != subject:
        raise ScopeError("记忆不属于当前人物")
    if (
        fact["status"] not in statuses
        or fact.get("consent") != "granted"
        or fact.get("assertion_status") != "user_asserted"
        or memory.repo.is_revoked(owner, "fact", ident)
    ):
        raise EvidenceError("记忆已失效或未获授权")
    verify_originals(memory, owner, subject, fact.get("source_refs", []))
    proofs = fact.get("category_consent_ids", [])
    if not isinstance(proofs, list) or any(not isinstance(item, str) for item in proofs):
        raise EvidenceError("记忆授权结构无效")
    if fact.get("approval_consent_id"):
        proofs = [*proofs, fact["approval_consent_id"]]
    for ident in proofs:
        if not isinstance(ident, str) or not consent_live(
            memory, owner, subject, memory.repo.get(owner, "consent", ident)
        ):
            raise EvidenceError("记忆授权已失效")
    for ref in fact["source_refs"]:
        source = memory.get_source(owner, ref["message_id"])
        policy = source.get("policy", {})
        if (
            policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or source.get("thread_id") != "life:" + subject
            or has_optout(source["content"])
        ):
            raise EvidenceError("来源不属于已授权长期记忆")
    _sensitive_authority(memory, owner, subject, fact)
    return fact


def _sensitive_authority(memory: MemoryService, owner: str, subject: str, fact: dict[str, Any]) -> None:
    for ref in fact["source_refs"]:
        if ref["quote"] != fact.get("content"):
            continue
        source = memory.get_source(owner, ref["message_id"])
        level = sensitivity(ref["quote"], source["content"], ref["start"], ref["end"])
        if level not in SENSITIVITIES:
            return
        categories = sensitivity_categories(ref["quote"], source["content"], ref["start"], ref["end"])
        approval = fact.get("approval_consent_id")
        if approval:
            proof = memory.repo.get(owner, "consent", approval)
            if (
                proof.get("message_id") == source["id"]
                and proof.get("scope_start") == ref["start"]
                and proof.get("scope_end") == ref["end"]
                and set(categories) <= set(proof.get("categories", []))
            ):
                return
        if categories_granted(memory, owner, subject, categories):
            return
        clause = authorization_clause(source["content"], ref["start"], ref["end"])
        if explicit_save_authorization(clause):
            return
        raise EvidenceError("敏感记忆尚缺当前可核验的保存授权")
    raise EvidenceError("记忆缺少与正文对应的原话范围")


def statement_instant(memory: MemoryService, owner: str, fact: dict[str, Any]) -> datetime:
    """Use the original assertion's clock, never its later approval or import time."""
    for ref in fact["source_refs"]:
        if ref["quote"] != fact.get("content"):
            continue
        source = memory.get_source(owner, ref["message_id"])
        instant = history_instant(source.get("at"))
        if instant is None or fact.get("said_at") and history_instant(fact["said_at"]) != instant:
            raise EvidenceError("记忆说法时间与原话不一致")
        return instant
    raise EvidenceError("记忆缺少对应原话时刻")

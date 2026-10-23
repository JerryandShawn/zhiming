"""Consume existing P3 sensitive proposals using authenticated, current user actions."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.agent_tools_policy import (
    KIND_MAP,
    SENSITIVITIES,
    V4FactMemory,
    sensitivity_categories,
)
from mingjing_core.application.memory2_conflicts import checked_conflict
from mingjing_core.application.memory2_consent import consent_live
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

SAVE_ONCE = "请保存这条记忆"
SAVE_CATEGORY = "请保存这条记忆，以后这类都记"
META_FIELDS = frozenset({"summary", "requested_kind", "said_at", "owner_timezone", "event_at", "original_expression"})


def approval_reference(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "message_id": action["id"],
        "version": action["revision"],
        "start": 0,
        "end": len(action["content"]),
        "quote": action["content"],
    }


def require_current_action(action: dict[str, Any], command: str) -> None:
    policy = action.get("policy", {})
    if action["content"] != command or policy.get("origin") != "current_user" or policy.get("run_context") is not True:
        raise EvidenceError("需要当前用户明确确认所选记忆提案")


class MemoryProposalService:
    """Route authentication supplies owner; no model-provided consent booleans are accepted."""

    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = V4FactMemory(memory.repo), memory.repo

    def accept(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        *,
        expected_revision: int,
        message_id: str,
        remember_category: bool,
        operation_id: str,
    ) -> dict[str, Any]:
        if type(remember_category) is not bool or type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("记忆确认参数无效")
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            command = SAVE_CATEGORY if remember_category else SAVE_ONCE
            require_current_action(action, command)
            payload = {
                "subject": subject,
                "proposal_id": proposal_id,
                "expected_revision": expected_revision,
                "message_id": message_id,
                "remember_category": remember_category,
            }
            receipt = self.repo.mutation_request(
                owner,
                "memory2_proposal_accept",
                operation_id,
                payload,
                partial(
                    self._apply,
                    connection,
                    owner,
                    subject,
                    proposal_id,
                    expected_revision,
                    action,
                    remember_category,
                    operation_id,
                ),
            )
            fact = self.repo.get(owner, "fact", receipt["fact_id"], include_deleted=True)
            if fact["status"] != "active" or self.repo.is_revoked(owner, "fact", fact["id"]):
                raise EvidenceError("原确认结果已失效")
            verify_originals(self.memory, owner, subject, fact["source_refs"])
            return receipt

    def reject(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        *,
        expected_revision: int,
        message_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, "不要保存这条记忆")
            payload = {
                "subject": subject,
                "proposal_id": proposal_id,
                "revision": expected_revision,
                "message_id": message_id,
            }
            return self.repo.mutation_request(
                owner,
                "memory2_proposal_reject",
                operation_id,
                payload,
                partial(self._reject, owner, subject, proposal_id, expected_revision, operation_id),
            )

    def _reject(self, owner: str, subject: str, ident: str, revision: int, operation_id: str) -> dict[str, Any]:
        proposal = self._pending(owner, subject, ident, revision, allow_conflict=True)
        deleted = self.repo.delete(
            owner, "proposal", ident, expected_revision=proposal["revision"], operation_id=operation_id + ":reject"
        )
        return {
            "write_status": "stopped",
            "id": ident,
            "kind": "proposal",
            "revision": deleted["revision"],
            "code": "proposal_rejected",
        }

    def _pending(
        self, owner: str, subject: str, ident: str, revision: int, *, allow_conflict: bool = False
    ) -> dict[str, Any]:
        proposal = self.repo.get(owner, "proposal", ident)
        if proposal["subject_id"] != subject:
            raise ScopeError("记忆提案不属于当前人物")
        if proposal["revision"] != revision:
            raise RevisionConflict("记忆提案已经变化")
        if proposal.get("proposal_type") == "memory_conflict":
            if not allow_conflict:
                raise EvidenceError("冲突提案需要先明确选择哪条说法为准")
            checked_conflict(self.memory, owner, subject, proposal)
            return proposal
        if proposal["status"] != "pending" or proposal.get("sensitivity") not in SENSITIVITIES:
            raise EvidenceError("此提案不能用作敏感记忆授权")
        refs = proposal.get("source_refs", [])
        if len(refs) != 1:
            raise EvidenceError("记忆提案需要唯一原话范围")
        verify_originals(self.memory, owner, subject, refs)
        return proposal

    def _consent(
        self, owner: str, subject: str, proposal: dict[str, Any], action: dict[str, Any], operation_id: str
    ) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
        ref = proposal["source_refs"][0]
        source = self.memory.get_source(owner, ref["message_id"])
        before, after = history_instant(source.get("at")), history_instant(action.get("at"))
        if before is None or after is None or after < before or source["id"] == action["id"]:
            raise EvidenceError("确认消息必须在原话之后")
        categories = sensitivity_categories(
            ref["quote"], source["content"], ref["start"], ref["end"], proposal["sensitivity"]
        )
        ident = "consent_" + fingerprint([owner, action["id"]])[:32]
        kind = KIND_MAP.get(proposal["kind"], proposal["kind"])
        proof = self.repo.put(
            owner,
            "consent",
            ident,
            {
                "authority": "p5_proposal",
                "proposal_id": proposal["id"],
                "message_id": source["id"],
                "source_revision": source["revision"],
                "scope_start": ref["start"],
                "scope_end": ref["end"],
                "approval_message_id": action["id"],
                "approval_revision": action["revision"],
                "approval_start": 0,
                "approval_end": len(action["content"]),
                "kinds": [kind],
                "categories": list(categories),
                "case_id": proposal.get("case_id"),
            },
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":consent",
        )
        if not consent_live(self.memory, owner, subject, proof):
            raise EvidenceError("原话或确认消息已经失效")
        return proof, source, categories

    def _apply(
        self,
        connection: Any,
        owner: str,
        subject: str,
        ident: str,
        revision: int,
        action: dict[str, Any],
        remember: bool,
        operation_id: str,
    ) -> dict[str, Any]:
        proposal = self._pending(owner, subject, ident, revision)
        proof, source, categories = self._consent(owner, subject, proposal, action, operation_id)
        ref = proposal["source_refs"][0]
        row = self.memory.save_fact(
            owner,
            subject,
            source["id"],
            ref["quote"],
            KIND_MAP.get(proposal["kind"], proposal["kind"]),
            case_id=proposal.get("case_id"),
            authorization_id=proof["id"],
            operation_id=operation_id + ":fact",
        )
        if row.get("write_status") != "saved":
            raise EvidenceError("已确认的记忆仍未满足保存规则")
        row = self._decorate(owner, proposal, action, source, row, proof["id"], operation_id)
        previous = self._grant(connection, owner, subject, categories, proof["id"]) if remember else None
        after = self._memory_settings(owner, subject) if remember else None
        self.repo.update(
            owner,
            "proposal",
            ident,
            {
                "status": "accepted",
                "fact_id": row["id"],
                "fact_ids": [row["id"]],
                "consent_id": proof["id"],
                "accepted_revision": row["revision"],
                "source_refs": row["source_refs"],
                "memory_settings_before": previous,
                "memory_settings_after": after,
                "proposal_before": proposal,
            },
            expected_revision=revision,
            operation_id=operation_id + ":accept",
        )
        return {
            "write_status": "saved",
            "id": row["id"],
            "fact_id": row["id"],
            "kind": "fact",
            "revision": row["revision"],
            "ids": [ident],
        }

    def _decorate(
        self,
        owner: str,
        proposal: dict[str, Any],
        action: dict[str, Any],
        source: dict[str, Any],
        row: dict[str, Any],
        proof_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        metadata = proposal.get("fact_metadata", {})
        if not isinstance(metadata, dict) or set(metadata) - META_FIELDS:
            raise EvidenceError("提案中的记忆字段无效")
        if proposal["kind"] == "event" and not metadata.get("event_at"):
            raise EvidenceError("事件提案缺少已经核实的绝对日期")
        metadata = dict(metadata, summary=proposal["summary"], requested_kind=proposal["kind"])
        metadata.setdefault("said_at", history_instant(source["at"]).isoformat())
        metadata.update(source_refs=[*row["source_refs"], approval_reference(action)], approval_consent_id=proof_id)
        return self.repo.update(
            owner,
            "fact",
            row["id"],
            metadata,
            expected_revision=row["revision"],
            operation_id=operation_id + ":metadata",
        )

    def _memory_settings(self, owner: str, subject: str) -> dict[str, Any]:
        settings = self.repo.assert_scope(owner, subject)["settings"]
        return {
            key: settings[key] for key in ("auto_save_categories", "memory_category_authorizations") if key in settings
        }

    def _grant(
        self, connection: Any, owner: str, subject: str, categories: tuple[str, ...], proof_id: str
    ) -> dict[str, Any]:
        settings = self.repo.assert_scope(owner, subject)["settings"]
        names = settings.get("auto_save_categories", [])
        proofs = settings.get("memory_category_authorizations", {})
        if (
            not isinstance(names, list)
            or any(not isinstance(item, str) for item in names)
            or not isinstance(proofs, dict)
        ):
            raise EvidenceError("现有记忆分类授权配置无效")
        before = {
            key: settings[key] for key in ("auto_save_categories", "memory_category_authorizations") if key in settings
        }
        updated = dict(settings, auto_save_categories=list(dict.fromkeys([*names, *categories])))
        updated["memory_category_authorizations"] = dict(proofs, **dict.fromkeys(categories, proof_id))
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(self.repo.table("core_owners")),
            (Jsonb(updated), owner),
        )
        self.repo.bump_revision(connection, owner, owner_scope=True)
        return before

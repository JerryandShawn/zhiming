"""Undo proposal acceptance and its dependent category-authorized facts atomically."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory2_proposals import approval_reference
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

MEMORY_KEYS = ("auto_save_categories", "memory_category_authorizations")


class MemoryProposalUndoService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

    def undo(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        *,
        expected_revision: int,
        message_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            if (
                action["content"] != "撤销这次记忆确认"
                or action.get("policy", {}).get("origin") != "current_user"
                or action.get("policy", {}).get("run_context") is not True
            ):
                raise EvidenceError("需要当前用户明确撤销所选记忆确认")
            payload = {
                "subject": subject,
                "proposal_id": proposal_id,
                "revision": expected_revision,
                "message_id": message_id,
            }
            return self.repo.mutation_request(
                owner,
                "memory2_proposal_undo",
                operation_id,
                payload,
                partial(self._apply, connection, owner, subject, proposal_id, expected_revision, operation_id),
            )

    def _apply(
        self, connection: Any, owner: str, subject: str, ident: str, revision: int, operation_id: str
    ) -> dict[str, Any]:
        proposal = self.repo.get(owner, "proposal", ident)
        if proposal["subject_id"] != subject:
            raise ScopeError("记忆确认不属于当前人物")
        if proposal["revision"] != revision:
            raise RevisionConflict("记忆确认已经变化")
        if proposal["status"] != "accepted" or not isinstance(proposal.get("proposal_before"), dict):
            raise EvidenceError("此记忆确认不能撤销")
        verify_originals(self.memory, owner, subject, proposal["source_refs"])
        target = self.repo.get(owner, "fact", proposal["fact_id"])
        if target["revision"] != proposal["accepted_revision"] or target["status"] != "active":
            raise RevisionConflict("确认后的记忆已再次变化")
        self._settings(connection, owner, subject, proposal)
        proof = self.repo.get(owner, "consent", proposal["consent_id"])
        affected = self._retire(owner, subject, proof["id"], operation_id)
        self.repo.delete(
            owner, "consent", proof["id"], expected_revision=proof["revision"], operation_id=operation_id + ":consent"
        )
        restored = self.repo.put(
            owner,
            "proposal",
            ident,
            proposal["proposal_before"],
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=revision,
            operation_id=operation_id + ":restore",
        )
        self.repo.invalidate_derived(owner, affected, [], recomputable=True)
        return {
            "write_status": "stopped",
            "id": ident,
            "kind": "proposal",
            "revision": restored["revision"],
            "affected_ids": affected,
        }

    def _retire(self, owner: str, subject: str, proof_id: str, operation_id: str) -> list[str]:
        affected = []
        for row in self.repo.list(owner, "fact", subject=subject):
            if row.get("approval_consent_id") != proof_id and proof_id not in row.get("category_consent_ids", []):
                continue
            if row["status"] in {"retired", "deleted", "stopped"}:
                continue
            self.repo.update(
                owner,
                "fact",
                row["id"],
                {"status": "retired"},
                expected_revision=row["revision"],
                operation_id=operation_id + ":retire:" + row["id"],
            )
            affected.append(row["id"])
        return affected

    def _settings(self, connection: Any, owner: str, subject: str, proposal: dict[str, Any]) -> None:
        before, after = proposal.get("memory_settings_before"), proposal.get("memory_settings_after")
        if before is None:
            return
        settings = self.repo.assert_scope(owner, subject)["settings"]
        current = {key: settings[key] for key in MEMORY_KEYS if key in settings}
        if current != after:
            raise RevisionConflict("分类授权已被再次修改，不能覆盖")
        updated = {key: value for key, value in settings.items() if key not in MEMORY_KEYS}
        updated.update(before)
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(self.repo.table("core_owners")),
            (Jsonb(updated), owner),
        )
        self.repo.bump_revision(connection, owner, owner_scope=True)

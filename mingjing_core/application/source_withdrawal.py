"""Explicit versioned deletion of an original and its owner-local derived closure."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.private import require_persistent_source


class SourceWithdrawalService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

    def delete(
        self, owner: str, subject: str, message_id: str, *, expected_revision: int, request_id: str
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("删除来源需要明确版本")
        # Scope checks precede a cached receipt; another owner cannot replay it.
        source = self.repo.get(owner, "message", message_id, include_deleted=True)
        if source["subject_id"] != subject:
            raise ScopeError("来源消息不属于当前人物")

        def effect():
            current = self.repo.get(owner, "message", message_id, include_deleted=True)
            if current["revision"] != expected_revision:
                raise RevisionConflict("来源在删除前已改变")
            require_persistent_source(current)
            if current.get("role") != "user" or current["status"] != "active":
                raise EvidenceError("只能通过此入口删除有效用户原话")
            facts = [
                fact
                for fact in self.repo.list(owner, "fact", subject=subject)
                if message_id in fact.get("source_ids", [])
                or any(ref.get("message_id") == message_id for ref in fact.get("source_refs", []))
            ]
            self.repo.delete(owner, "message", message_id, expected_revision=expected_revision)
            affected = []
            for fact in facts:
                self.memory.retire_fact(owner, fact["id"], expected_revision=fact["revision"])
                affected.append(fact["id"])
            self.repo.invalidate_derived(owner, affected, [message_id])
            for upload in self.repo.list(owner, "upload", subject=subject):
                if upload.get("message_id") == message_id:
                    self.repo.delete(owner, "upload", upload["id"], expected_revision=upload["revision"])
            if self.memory.on_revoke:
                self.memory.on_revoke(owner, affected, [message_id])
            erased = self.repo.get(owner, "message", message_id, include_deleted=True)
            return {
                "write_status": "deleted",
                "kind": "message",
                "id": message_id,
                "message_id": message_id,
                "revision": erased["revision"],
                "affected_ids": affected,
            }

        return self.repo.mutation_request(
            owner,
            "source_delete",
            request_id,
            {"subject": subject, "message_id": message_id, "expected_revision": expected_revision},
            effect,
        )

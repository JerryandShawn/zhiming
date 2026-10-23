"""Undo explicit conflict choices and their category-authorized effects atomically."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_conflict_resolution import (
    bind_action,
    checked_resolution,
)
from mingjing_core.application.memory2_conflicts import checked_conflict
from mingjing_core.application.memory2_proposal_undo import MemoryProposalUndoService
from mingjing_core.application.memory2_proposals import (
    approval_reference,
    require_current_action,
)
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

UNDO_CONFLICT = "撤销这次冲突选择"


class MemoryConflictUndoService:
    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo, self.clock = memory, memory.repo, clock or get_clock()
        self.confirmations = MemoryProposalUndoService(memory)

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
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("冲突撤销修订无效")
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, UNDO_CONFLICT)
            at = history_instant(action.get("at"))
            if at is None or at > self.clock.now():
                raise EvidenceError("冲突撤销的用户操作时间无效")
            bind_action(self.repo, owner, subject, proposal_id, action, operation_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_conflict_undo",
                operation_id,
                {
                    "subject": subject,
                    "proposal_id": proposal_id,
                    "revision": expected_revision,
                    "message_id": message_id,
                },
                partial(self._apply, connection, owner, subject, proposal_id, expected_revision, operation_id),
            )
            pending = self.repo.get(owner, "proposal", proposal_id)
            old = checked_conflict(self.memory, owner, subject, pending)
            if old["id"] != receipt["fact_id"] or old["revision"] != receipt["revision"]:
                raise EvidenceError("原冲突撤销回执已失效")
            return receipt

    def _apply(
        self, connection: Any, owner: str, subject: str, ident: str, revision: int, operation_id: str
    ) -> dict[str, Any]:
        proposal = self.repo.get(owner, "proposal", ident)
        if proposal["revision"] != revision:
            raise RevisionConflict("冲突选择已再次变化")
        old, new = checked_resolution(self.memory, owner, subject, proposal)
        affected = []
        if new is not None:
            self.confirmations._settings(connection, owner, subject, proposal)
            proof = self.repo.get(owner, "consent", proposal["consent_id"])
            affected = self.confirmations._retire(owner, subject, proof["id"], operation_id)
            self.repo.delete(
                owner,
                "consent",
                proof["id"],
                expected_revision=proof["revision"],
                operation_id=operation_id + ":revoke-consent",
            )
            before = proposal["old_before"]
            old = self.repo.put(
                owner,
                "fact",
                old["id"],
                before,
                subject=subject,
                case_id=old.get("case_id"),
                expected_revision=old["revision"],
                operation_id=operation_id + ":restore-old",
            )
        # Restore pending before cascading: it no longer depends on the retired new
        # fact. The monotonic target revision must point at the actually restored row.
        self.repo.put(
            owner,
            "proposal",
            ident,
            dict(proposal["proposal_before"], target_revision=old["revision"]),
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=revision,
            operation_id=operation_id + ":restore-proposal",
        )
        self.repo.invalidate_derived(owner, affected, [], recomputable=True, seed_entities=[("proposal", ident)])
        return {
            "write_status": "saved",
            "code": "memory2_conflict_undo",
            "fact_id": old["id"],
            "revision": old["revision"],
            "ids": [ident],
            "affected_ids": affected,
        }

"""Undo a combined slot replacement and sensitive confirmation without reviving withdrawn data."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_confirmed_slots import ACTIVE, MemoryConfirmedSlotService
from mingjing_core.application.memory2_fact_authority import authorized_fact
from mingjing_core.application.memory2_proposal_undo import MemoryProposalUndoService
from mingjing_core.application.memory2_proposals import approval_reference, require_current_action
from mingjing_core.application.memory2_slots_undo import MemorySlotUndoService
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

UNDO_CONFIRMED_SLOT = "撤销这次记忆更新和确认"


class MemoryConfirmedSlotUndoService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo
        self.slots = MemorySlotUndoService(memory)
        self.confirmations = MemoryProposalUndoService(memory)

    def undo(
        self,
        owner: str,
        subject: str,
        change_id: str,
        *,
        expected_revision: int,
        message_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("确认更新撤销修订无效")
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, UNDO_CONFIRMED_SLOT)
            if action.get("thread_id") != "life:" + subject:
                raise EvidenceError("撤销操作不属于当前长期记忆线程")
            payload = dict(subject=subject, change_id=change_id, revision=expected_revision, message_id=message_id)
            self.repo.mutation_request(
                owner,
                "memory2_confirmed_slot_undo_action",
                action["id"],
                dict(payload, operation_id=operation_id),
                lambda: {"status": "bound"},
            )
            receipt = self.repo.mutation_request(
                owner,
                "memory2_confirmed_slot_undo",
                operation_id,
                payload,
                partial(self._apply, connection, owner, subject, change_id, expected_revision, action, operation_id),
            )
            self._verify_result(owner, subject, receipt)
            return receipt

    def _checked(self, owner: str, subject: str, change_id: str, revision: int, action: dict) -> tuple[dict, dict]:
        change = self.repo.get(owner, "proposal", change_id)
        if change["subject_id"] != subject:
            raise ScopeError("确认更新不属于当前人物")
        if change.get("kind") != "memory2_slot_undo" or not change.get("confirmation_id"):
            raise EvidenceError("此变更不是敏感确认与槽更新的组合")
        if change["revision"] != revision:
            raise RevisionConflict("确认更新已再次变化")
        receipt = dict(
            ids=[change_id, change.get("confirmation_id")],
            fact_id=change["new_before"]["id"],
            revision=change["new_revision"],
            context_revision=revision,
        )
        change, proposal = MemoryConfirmedSlotService(self.memory).checked(owner, subject, receipt)
        verify_originals(self.memory, owner, subject, proposal["source_refs"])
        proof = self.repo.get(owner, "consent", change["consent_id"])
        approval = self.memory.get_source(owner, proof["approval_message_id"])
        before, at = history_instant(approval.get("at")), history_instant(action.get("at"))
        if (
            before is None
            or at is None
            or not before <= at <= get_clock().now()
            or action["created_at"] < change["updated_at"]
            or action["created_at"] < proposal["updated_at"]
        ):
            raise EvidenceError("撤销原话必须晚于确认且不在未来")
        return change, proposal

    def _apply(
        self,
        connection: Any,
        owner: str,
        subject: str,
        change_id: str,
        revision: int,
        action: dict,
        operation_id: str,
    ) -> dict:
        change, proposal = self._checked(owner, subject, change_id, revision, action)
        self.confirmations._settings(connection, owner, subject, proposal)
        # The restored pending proposal depends on valid originals, not the new
        # fact; detach it before invalidation clears snapshots of the new value.
        pending = self.repo.put(
            owner,
            "proposal",
            proposal["id"],
            proposal["proposal_before"],
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=proposal["revision"],
            operation_id=operation_id + ":pending",
        )
        restored = self.slots._apply(owner, subject, change_id, revision, operation_id + ":slot")
        affected = self.confirmations._retire(owner, subject, change["consent_id"], operation_id)
        proof = self.repo.get(owner, "consent", change["consent_id"])
        self.repo.delete(
            owner, "consent", proof["id"], expected_revision=proof["revision"], operation_id=operation_id + ":consent"
        )
        affected = list(dict.fromkeys([change["new_before"]["id"], *affected]))
        self.repo.invalidate_derived(
            owner, affected, [], recomputable=True, seed_entities=[("proposal", pending["id"])]
        )
        guard = self._record_result(owner, subject, restored, pending, proof["id"], operation_id)
        return dict(
            restored,
            code="memory2_confirmed_slot_undo",
            affected_ids=affected,
            ids=[*restored["ids"], pending["id"], proof["id"], guard["id"]],
        )

    def _record_result(self, owner: str, subject: str, restored: dict, pending: dict, proof_id: str, operation_id: str):
        old = self.repo.get(owner, "fact", restored["fact_id"])
        new = self.repo.get(owner, "fact", restored["ids"][0])
        # Keep only identifiers/revisions; future source/fact invalidation can
        # retire this guard without retaining another sensitive text snapshot.
        sources = {ref["message_id"] for row in (old, pending) for ref in row["source_refs"]}
        return self.repo.put(
            owner,
            "proposal",
            "memory2_undo_guard_" + fingerprint([owner, operation_id])[:32],
            dict(
                kind="memory2_confirmed_slot_undo_result",
                status="applied",
                source_ids=sorted(sources),
                fact_ids=[old["id"], new["id"]],
                pending_id=pending["id"],
                pending_revision=pending["revision"],
                retired_revision=new["revision"],
                consent_id=proof_id,
            ),
            subject=subject,
            case_id=old.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":guard",
        )

    def _verify_result(self, owner: str, subject: str, receipt: dict) -> None:
        old = authorized_fact(self.memory, owner, subject, receipt["fact_id"], statuses=ACTIVE)
        new = self.repo.get(owner, "fact", receipt["ids"][0], include_deleted=True)
        guard = self.repo.get(owner, "proposal", receipt["ids"][3])
        pending = self.repo.get(owner, "proposal", receipt["ids"][1])
        proof = self.repo.get(owner, "consent", receipt["ids"][2], include_deleted=True)
        verify_originals(self.memory, owner, subject, pending["source_refs"])
        if (
            guard["subject_id"] != subject
            or guard["status"] != "applied"
            or guard.get("kind") != "memory2_confirmed_slot_undo_result"
            or guard.get("fact_ids") != [old["id"], new["id"]]
            or guard.get("pending_id") != pending["id"]
            or guard.get("consent_id") != proof["id"]
            or old["revision"] != receipt["revision"]
            or new["status"] != "retired"
            or new["revision"] != guard["retired_revision"]
            or proof["status"] != "deleted"
            or not self.repo.is_revoked(owner, "consent", proof["id"])
            or pending["status"] != "pending"
            or pending["revision"] != guard["pending_revision"]
        ):
            raise EvidenceError("原确认更新撤销结果已经失效")

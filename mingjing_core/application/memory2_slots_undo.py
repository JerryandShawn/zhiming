"""Undo a single-slot transition without restoring retired or withdrawn evidence."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_fact_authority import authorized_fact
from mingjing_core.application.memory2_proposals import approval_reference, require_current_action
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

ACTIVE = frozenset({"active"})


class MemorySlotUndoService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

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
            raise EvidenceError("单值记忆撤销修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, "撤销这次记忆更新")
            receipt = self.repo.mutation_request(
                owner,
                "memory2_slot_undo",
                operation_id,
                {"subject": subject, "id": change_id, "revision": expected_revision, "message_id": message_id},
                partial(self._apply, owner, subject, change_id, expected_revision, operation_id),
            )
            restored = authorized_fact(self.memory, owner, subject, receipt["fact_id"], statuses=ACTIVE)
            retired = authorized_fact(self.memory, owner, subject, receipt["ids"][0], statuses=frozenset({"retired"}))
            if restored["revision"] != receipt["revision"] or retired.get("supersedes") != restored["id"]:
                raise EvidenceError("原单值记忆撤销回执已失效")
            return receipt

    def _apply(self, owner: str, subject: str, change_id: str, revision: int, operation_id: str) -> dict[str, Any]:
        change = self.repo.get(owner, "proposal", change_id)
        if change["subject_id"] != subject:
            raise ScopeError("记忆更新不属于当前人物")
        if change["revision"] != revision:
            raise RevisionConflict("记忆更新变更已变化")
        if change["status"] != "applied" or change.get("kind") != "memory2_slot_undo":
            raise EvidenceError("此记忆更新不能撤销")
        verify_originals(self.memory, owner, subject, change["source_refs"])
        before = change["old_before"]
        old = authorized_fact(self.memory, owner, subject, before["id"], statuses=ACTIVE)
        new = authorized_fact(self.memory, owner, subject, change["new_before"]["id"], statuses=ACTIVE)
        if old["revision"] != change["old_revision"] or new["revision"] != change["new_revision"]:
            raise RevisionConflict("更新后的记忆已再次变化")
        if old.get("superseded_by") != new["id"] or new.get("supersedes") != old["id"]:
            raise EvidenceError("记忆更新链不一致")
        restored = self.repo.put(
            owner,
            "fact",
            old["id"],
            before,
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=old["revision"],
            operation_id=operation_id + ":restore",
        )
        self.repo.update(
            owner,
            "fact",
            new["id"],
            {"status": "retired"},
            expected_revision=new["revision"],
            operation_id=operation_id + ":retire-new",
        )
        # Retired new-value claims cannot keep influencing downstream content. This
        # also clears the change snapshot; replay uses the body-free mutation receipt.
        self.repo.invalidate_derived(owner, [new["id"]], [], recomputable=True)
        return {
            "write_status": "saved",
            "code": "memory2_slot_undo",
            "fact_id": restored["id"],
            "revision": restored["revision"],
            "ids": [new["id"]],
        }

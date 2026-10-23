"""An explicit archive undo restores business fields without reviving withdrawn sources."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_archive import MemoryArchiveService
from mingjing_core.application.memory2_proposals import approval_reference, require_current_action
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


class MemoryArchiveUndoService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo
        self.archives = MemoryArchiveService(memory)

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
            raise EvidenceError("归档撤销修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, "撤销这次记忆归档")
            receipt = self.repo.mutation_request(
                owner,
                "memory2_archive_undo",
                operation_id,
                {"subject": subject, "id": change_id, "revision": expected_revision, "message_id": message_id},
                partial(self._apply, owner, subject, change_id, expected_revision, operation_id),
            )
            fact = self.archives._check_fact(owner, subject, receipt["fact_id"])
            change = self.repo.get(owner, "proposal", change_id)
            if fact["status"] != "active" or fact["revision"] != receipt["revision"] or change["status"] != "undone":
                raise EvidenceError("原归档撤销回执已失效")
            return receipt

    def _apply(
        self, owner: str, subject: str, change_id: str, expected_revision: int, operation_id: str
    ) -> dict[str, Any]:
        change = self.repo.get(owner, "proposal", change_id)
        if change["subject_id"] != subject:
            raise ScopeError("归档撤销不属于当前人物")
        if change["revision"] != expected_revision:
            raise RevisionConflict("归档变更已再次修改")
        if change["status"] != "applied" or change.get("kind") != "memory2_archive_undo":
            raise EvidenceError("此归档变更不能撤销")
        verify_originals(self.memory, owner, subject, change["source_refs"])
        before = change["before"]
        archived = self.archives._check_fact(owner, subject, before["id"])
        if archived["status"] != "archived" or archived["revision"] != change["target_revision"]:
            raise RevisionConflict("归档后的记忆已再次变化")
        restored = self.repo.put(
            owner,
            "fact",
            before["id"],
            before,
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=archived["revision"],
            operation_id=operation_id + ":restore",
        )
        self.repo.update(
            owner,
            "proposal",
            change_id,
            {"status": "undone"},
            expected_revision=expected_revision,
            operation_id=operation_id + ":undone",
        )
        return {
            "write_status": "saved",
            "code": "memory2_archive_undo",
            "fact_id": restored["id"],
            "revision": restored["revision"],
        }

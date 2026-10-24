"""Apply R14 to actual admitted facts, preserving the existing exact slot undo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mingjing_core.application.memory2_slots import MemorySlotUpdateService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.change_signals import explicit_replacement_slot
from mingjing_core.memory.slots import normalize_slot

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


class MemoryExplicitChangeService:
    """Internal entry only: a caller must admit the new fact in its same transaction.

    The original fact-authority service still verifies sensitive consent. This
    service cannot grant permission, create a second fact, or weaken Agent proofs.
    """

    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo
        self.slots = MemorySlotUpdateService(memory)

    def update(
        self,
        owner: str,
        subject: str,
        old_id: str,
        new_id: str,
        *,
        expected_old_revision: int,
        expected_new_revision: int,
        operation_id: str,
    ) -> dict:
        with self.repo.transaction(owner):
            old, new = self.slots._facts(owner, subject, old_id, new_id)
            slot = explicit_replacement_slot(old.get("content", ""), new.get("content", ""))
            if slot is None or any(normalize_slot(row.get("slot")) not in {None, slot} for row in (old, new)):
                raise EvidenceError("原话没有足够明确的变化依据，应先确认")
            if not old.get("superseded_by"):
                peers = [
                    row["id"]
                    for row in self.memory.facts(owner, subject)
                    if row["id"] != new_id
                    and row.get("case_id") == old.get("case_id")
                    and explicit_replacement_slot(row.get("content", ""), new["content"]) == slot
                ]
                if peers != [old_id]:
                    raise EvidenceError("变化对应多条旧记忆，应先明确范围")
            return self.slots.update(
                owner,
                subject,
                old_id,
                new_id,
                slot=slot,
                expected_old_revision=expected_old_revision,
                expected_new_revision=expected_new_revision,
                operation_id=operation_id,
            )

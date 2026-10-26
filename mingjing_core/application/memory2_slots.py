"""Atomic single-slot transitions; caller must admit the new fact in the same transaction."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_fact_authority import authorized_fact, statement_instant
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.change_signals import explicit_replacement_slot
from mingjing_core.memory.slots import SLOTS, compatible_statement, normalize_slot
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

ACTIVE = frozenset({"active"})


class MemorySlotUpdateService:
    """Internal updated receipt is deliberately not wired past the mainline commit gate."""

    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo, self.clock = memory, memory.repo, clock or get_clock()

    def update(
        self,
        owner: str,
        subject: str,
        old_id: str,
        new_id: str,
        *,
        slot: str,
        expected_old_revision: int,
        expected_new_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        canonical = normalize_slot(slot)
        if canonical is None or SLOTS[canonical].cardinality != "single" or old_id == new_id:
            raise EvidenceError("更新需要明确的单值记忆槽及两个不同事实")
        if any(type(value) is not int or value < 1 for value in (expected_old_revision, expected_new_revision)):
            raise EvidenceError("单值记忆修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            old, new = self._facts(owner, subject, old_id, new_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_slot_update",
                operation_id,
                {
                    "subject": subject,
                    "old": old_id,
                    "new": new_id,
                    "slot": canonical,
                    "old_revision": expected_old_revision,
                    "new_revision": expected_new_revision,
                },
                partial(
                    self._apply,
                    owner,
                    subject,
                    old,
                    new,
                    canonical,
                    expected_old_revision,
                    expected_new_revision,
                    operation_id,
                ),
            )
            self._verify_receipt(owner, subject, old_id, new_id, receipt)
            return receipt

    def _facts(self, owner: str, subject: str, old_id: str, new_id: str) -> tuple[dict, dict]:
        old = authorized_fact(self.memory, owner, subject, old_id, statuses=ACTIVE)
        new = authorized_fact(self.memory, owner, subject, new_id, statuses=ACTIVE)
        if old.get("case_id") != new.get("case_id"):
            raise ScopeError("不同事项的记忆不能互相更新")
        return old, new

    def _validate(self, owner: str, subject: str, old: dict, new: dict, slot: str) -> str:
        explicit = explicit_replacement_slot(old.get("content", ""), new.get("content", "")) == slot
        old_matches = normalize_slot(old.get("slot")) == slot or not old.get("slot") and explicit
        if (
            not old_matches
            or normalize_slot(new.get("slot")) not in {None, slot}
            or any(row.get("valid_to") or row.get("superseded_by") for row in (old, new))
            or new.get("supersedes")
            or not compatible_statement(slot, new.get("content", ""))
            or not (compatible_statement(slot, old.get("content", "")) or explicit)
        ):
            raise EvidenceError("记忆槽不一致、含临时状态或更新链已有变化")
        before = statement_instant(self.memory, owner, old)
        after = statement_instant(self.memory, owner, new)
        if not before < after <= self.clock.now():
            raise EvidenceError("新说法须晚于旧说法且不在未来")
        starts = [history_instant(row.get("valid_from")) for row in (old, new)]
        if any(start is None or start > after for start in starts):
            raise EvidenceError("记忆有效期尚未开始或无法确认")
        peers = self.repo.list(owner, "fact", subject=subject)
        if any(
            row["id"] not in {old["id"], new["id"]}
            and row["status"] == "active"
            and row.get("case_id") == old.get("case_id")
            and normalize_slot(row.get("slot")) == slot
            and (slot != "preference" or explicit_replacement_slot(row.get("content", ""), new["content"]) == slot)
            and not row.get("valid_to")
            for row in peers
        ):
            raise EvidenceError("同槽存在多个候选，需要先确认")
        return after.isoformat()

    def _apply(
        self,
        owner: str,
        subject: str,
        old: dict,
        new: dict,
        slot: str,
        old_revision: int,
        new_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        if old["revision"] != old_revision or new["revision"] != new_revision:
            raise RevisionConflict("单值记忆已变化")
        closed_at = self._validate(owner, subject, old, new, slot)
        old_after = self.repo.update(
            owner,
            "fact",
            old["id"],
            {"valid_to": closed_at, "superseded_by": new["id"]},
            expected_revision=old_revision,
            operation_id=operation_id + ":close",
        )
        new_after = self.repo.update(
            owner,
            "fact",
            new["id"],
            {"slot": slot, "valid_from": closed_at, "supersedes": old["id"]},
            expected_revision=new_revision,
            operation_id=operation_id + ":open",
        )
        ident = self._record(owner, subject, old, new, old_after, new_after, operation_id)
        return {
            "write_status": "updated",
            "code": "memory2_slot_updated",
            "id": new["id"],
            "fact_id": new["id"],
            "kind": "fact",
            "revision": new_after["revision"],
            "ids": [ident],
            "affected_ids": [old["id"]],
        }

    def _record(
        self, owner: str, subject: str, old: dict, new: dict, old_after: dict, new_after: dict, operation_id: str
    ) -> str:
        ident = "memory2_slot_" + fingerprint([owner, operation_id])[:32]
        refs = [*old["source_refs"], *new["source_refs"]]
        self.repo.put(
            owner,
            "proposal",
            ident,
            {
                "kind": "memory2_slot_undo",
                "status": "applied",
                "old_before": old,
                "new_before": new,
                "fact_ids": [old["id"], new["id"]],
                "source_refs": refs,
                "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
                "old_revision": old_after["revision"],
                "new_revision": new_after["revision"],
            },
            subject=subject,
            case_id=old.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":change",
        )
        return ident

    def _verify_receipt(self, owner: str, subject: str, old_id: str, new_id: str, receipt: dict) -> None:
        old, new = self._facts(owner, subject, old_id, new_id)
        change = self.repo.get(owner, "proposal", receipt["ids"][0])
        if (
            change["status"] != "applied"
            or change.get("kind") != "memory2_slot_undo"
            or change.get("fact_ids") != [old_id, new_id]
            or new["revision"] != receipt["revision"]
            or new["revision"] != change["new_revision"]
            or old["revision"] != change["old_revision"]
            or new.get("supersedes") != old_id
            or old.get("superseded_by") != new_id
            or old.get("valid_to") != new.get("valid_from")
        ):
            raise EvidenceError("原单值记忆更新回执已失效")

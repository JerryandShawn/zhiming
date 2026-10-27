"""Undo a date answer atomically, reopening the same question against the restored fact revision."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_event_answers import MemoryEventAnswerService
from mingjing_core.application.memory2_event_dates import GAP_KIND
from mingjing_core.application.memory2_proposals import require_current_action
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

UNDO_DATE_ANSWER = "撤销这次事件日期确认"


class MemoryEventAnswerUndoService:
    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo = memory, memory.repo
        self.answers = MemoryEventAnswerService(memory, clock=clock)

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
            raise EvidenceError("事件日期确认撤销修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.answers.action(owner, subject, message_id)
            require_current_action(action, UNDO_DATE_ANSWER)
            payload = dict(
                subject=subject,
                id=change_id,
                revision=expected_revision,
                message_id=message_id,
                action_revision=action["revision"],
            )
            self.repo.mutation_request(
                owner,
                "memory2_event_answer_undo_action",
                message_id,
                dict(payload, operation_id=operation_id),
                lambda: {"status": "bound"},
            )
            receipt = self.repo.mutation_request(
                owner,
                "memory2_event_answer_undo",
                operation_id,
                payload,
                partial(self._apply, owner, subject, change_id, expected_revision, action, operation_id),
            )
            self._verify(owner, subject, change_id, receipt)
            return receipt

    def _checked(self, owner: str, subject: str, ident: str, revision: int, action: dict) -> tuple[dict, dict, dict]:
        change = self.repo.get(owner, "proposal", ident)
        if change["revision"] != revision:
            raise RevisionConflict("事件日期确认变更已修改")
        if len(change.get("fact_ids", [])) != 1 or not change.get("gap_id"):
            raise EvidenceError("不是可撤销的事件日期确认")
        receipt = dict(
            fact_id=change["fact_ids"][0],
            revision=change.get("target_revision"),
            ids=[ident, change["gap_id"]],
            context_revision=revision,
        )
        change, fact, gap = self.answers.checked(owner, subject, receipt)
        confirmed = history_instant(change.get("confirmed_at"))
        if (
            action["created_at"] < change["updated_at"]
            or confirmed is None
            or history_instant(action["at"]) < confirmed
        ):
            raise EvidenceError("撤销原话必须晚于日期确认")
        return change, fact, gap

    def _apply(self, owner: str, subject: str, ident: str, revision: int, action: dict, operation_id: str) -> dict:
        change, fact, gap = self._checked(owner, subject, ident, revision, action)
        before = change["before"]
        if before["id"] != fact["id"] or before.get("event_at"):
            raise EvidenceError("事件日期确认前态无效")
        restored = self.repo.put(
            owner,
            "fact",
            fact["id"],
            before,
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=fact["revision"],
            operation_id=operation_id + ":restore",
        )
        # Detach only inside this owner transaction. Restore dependencies before
        # committing, so a later forget still clears this same reopened question.
        detached = self.repo.put(
            owner,
            "knowledge_gap",
            gap["id"],
            dict(kind=GAP_KIND, status="closed"),
            subject=subject,
            case_id=gap.get("case_id"),
            expected_revision=gap["revision"],
            operation_id=operation_id + ":detach",
        )
        self.repo.delete(owner, "proposal", ident, expected_revision=revision, operation_id=operation_id + ":close")
        self.repo.invalidate_derived(owner, [fact["id"]], [], recomputable=True)
        reopened = self.repo.put(
            owner,
            "knowledge_gap",
            gap["id"],
            dict(
                change["gap_before"],
                target_revision=restored["revision"],
                prepared_at=self.answers.repairs.clock.now().isoformat(),
            ),
            subject=subject,
            case_id=gap.get("case_id"),
            expected_revision=detached["revision"],
            operation_id=operation_id + ":reopen",
        )
        return dict(
            write_status="undone",
            code="memory2_event_answer_undo",
            fact_id=restored["id"],
            revision=restored["revision"],
            ids=[gap["id"]],
            context_revision=reopened["revision"],
        )

    def _verify(self, owner: str, subject: str, ident: str, receipt: dict) -> None:
        fact = self.answers.repairs.fact(owner, subject, receipt["fact_id"])
        gap = self.repo.get(owner, "knowledge_gap", receipt["ids"][0])
        change = self.repo.get(owner, "proposal", ident, include_deleted=True)
        if (
            fact.get("event_at")
            or fact["revision"] != receipt["revision"]
            or gap["revision"] != receipt["context_revision"]
            or self.repo.is_revoked(owner, "knowledge_gap", gap["id"])
            or change["status"] != "deleted"
            or not self.repo.is_revoked(owner, "proposal", ident)
        ):
            raise EvidenceError("原日期确认撤销结果已失效")
        self.answers.repairs.check_record(subject, fact, gap, GAP_KIND, "open")

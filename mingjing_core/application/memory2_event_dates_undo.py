"""Explicit date-repair undo and gap dismissal, guarded against stale or withdrawn originals."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_event_dates import CHANGE_KIND, GAP_KIND, MemoryEventTimeRepairService
from mingjing_core.application.memory2_fact_authority import statement_instant
from mingjing_core.application.memory2_proposals import approval_reference, require_current_action
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

UNDO_EVENT_DATE = "撤销这次事件日期整理"


class MemoryEventTimeUndoService:
    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo = memory, memory.repo
        self.repairs = MemoryEventTimeRepairService(memory, clock=clock)

    def undo(
        self,
        owner: str,
        subject: str,
        record_id: str,
        *,
        record_kind: str,
        expected_revision: int,
        message_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        if (
            record_kind not in {"proposal", "knowledge_gap"}
            or type(expected_revision) is not int
            or expected_revision < 1
        ):
            raise EvidenceError("事件日期撤销参数无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            require_current_action(action, UNDO_EVENT_DATE)
            at = history_instant(action.get("at"))
            if action.get("thread_id") != "life:" + subject or at is None or at > self.repairs.clock.now():
                raise EvidenceError("撤销不属于当前长期记忆线程或时刻无效")
            payload = dict(
                subject=subject,
                id=record_id,
                kind=record_kind,
                revision=expected_revision,
                message_id=message_id,
                action_revision=action["revision"],
            )
            self.repo.mutation_request(
                owner,
                "memory2_event_date_undo_action",
                action["id"],
                dict(payload, operation_id=operation_id),
                lambda: {"status": "bound"},
            )
            receipt = self.repo.mutation_request(
                owner,
                "memory2_event_date_undo",
                operation_id,
                payload,
                partial(self._apply, owner, subject, record_kind, record_id, expected_revision, action, operation_id),
            )
            fact = self.repairs.fact(owner, subject, receipt["fact_id"])
            tombstone = self.repo.get(owner, record_kind, record_id, include_deleted=True)
            if (
                fact["revision"] != receipt["revision"]
                or fact.get("event_at")
                or tombstone["status"] != "deleted"
                or not self.repo.is_revoked(owner, record_kind, record_id)
            ):
                raise EvidenceError("原事件日期撤销回执已失效")
            return receipt

    def _checked(
        self, owner: str, subject: str, kind: str, ident: str, revision: int, action: dict
    ) -> tuple[dict, dict]:
        record = self.repo.get(owner, kind, ident)
        if record["subject_id"] != subject:
            raise ScopeError("事件日期记录不属于当前人物")
        if self.repo.is_revoked(owner, kind, ident):
            raise EvidenceError("事件日期记录已撤销")
        if record["revision"] != revision:
            raise RevisionConflict("事件日期记录已再次修改")
        expected_kind = GAP_KIND if kind == "knowledge_gap" else CHANGE_KIND
        if record.get("kind") != expected_kind or len(record.get("fact_ids", [])) != 1:
            raise EvidenceError("不是可撤销的事件日期记录")
        fact = self.repairs.fact(owner, subject, record["fact_ids"][0])
        self.repairs.check_record(
            subject, fact, record, expected_kind, "open" if kind == "knowledge_gap" else "applied"
        )
        verify_originals(self.memory, owner, subject, record["source_refs"])
        at = history_instant(action.get("at"))
        if (
            at is None
            or not statement_instant(self.memory, owner, fact) <= at <= self.repairs.clock.now()
            or action["created_at"] < record["updated_at"]
        ):
            raise EvidenceError("撤销原话须晚于整理且不能在未来")
        return record, fact

    def _apply(
        self,
        owner: str,
        subject: str,
        kind: str,
        ident: str,
        revision: int,
        action: dict,
        operation_id: str,
    ) -> dict:
        record, fact = self._checked(owner, subject, kind, ident, revision, action)
        if kind == "proposal":
            before = record["before"]
            if before.get("event_at") or before.get("id") != fact["id"]:
                raise EvidenceError("日期整理前态无效")
            fact = self.repo.put(
                owner,
                "fact",
                fact["id"],
                before,
                subject=subject,
                case_id=before.get("case_id"),
                expected_revision=fact["revision"],
                operation_id=operation_id + ":restore",
            )
        self.repo.delete(owner, kind, ident, expected_revision=revision, operation_id=operation_id + ":close")
        if kind == "proposal":
            self.repo.invalidate_derived(owner, [fact["id"]], [], recomputable=True)
        return dict(
            write_status="undone", code="memory2_event_date_undo", fact_id=fact["id"], revision=fact["revision"]
        )

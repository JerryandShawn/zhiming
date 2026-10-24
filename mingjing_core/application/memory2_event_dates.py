"""Repair explicitly declared legacy events using their original clock and shared parser."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from mingjing_core.application.agent_tools_dates import valid_event_at
from mingjing_core.application.memory2_fact_authority import authorized_fact, statement_instant
from mingjing_core.application.time_range_parser import ModuleTimeRangeParser
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

ACTIVE = frozenset({"active"})
CHANGE_KIND = "memory2_event_date_undo"
GAP_KIND = "memory_time_confirmation"


class MemoryEventTimeRepairService:
    """Internal background service; no scheduler, tool or commit-gate changes."""

    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo, self.clock = memory, memory.repo, clock or get_clock()
        self.parser = ModuleTimeRangeParser()

    def repair(
        self, owner: str, subject: str, fact_id: str, *, expected_revision: int, operation_id: str
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("事件日期整理修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            self.fact(owner, subject, fact_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_event_date_repair",
                operation_id,
                dict(subject=subject, fact_id=fact_id, revision=expected_revision),
                partial(self._apply, owner, subject, fact_id, expected_revision, operation_id),
            )
            self._verify(owner, subject, fact_id, receipt)
            return receipt

    def fact(self, owner: str, subject: str, fact_id: str) -> dict:
        fact = authorized_fact(self.memory, owner, subject, fact_id, statuses=ACTIVE)
        if (
            fact.get("kind") != "event"
            and fact.get("requested_kind") != "event"
            or fact.get("superseded_by")
            or fact.get("valid_to")
        ):
            raise EvidenceError("只整理明确声明的当前事件")
        said_at = statement_instant(self.memory, owner, fact)
        if said_at > self.clock.now():
            raise EvidenceError("事件原话时刻不能在未来")
        zone = fact.get("owner_timezone")
        if not isinstance(zone, str) or not zone:
            raise EvidenceError("事件缺少原人物时区")
        try:
            ZoneInfo(zone)
        except (KeyError, ValueError) as exc:
            raise EvidenceError("事件人物时区无效") from exc
        return fact

    def _apply(self, owner: str, subject: str, fact_id: str, revision: int, operation_id: str) -> dict:
        before = self.fact(owner, subject, fact_id)
        if before["revision"] != revision:
            raise RevisionConflict("事件整理前记忆已变化")
        if before.get("event_at"):
            raise EvidenceError("已有事件日期不能被后台整理覆盖")
        said_at = statement_instant(self.memory, owner, before)
        result = self.parser.resolve(before["content"], said_at=said_at, timezone=before["owner_timezone"])
        if result.status in {"not_date", "needs_confirmation"}:
            return self._gap(owner, subject, before, result.reason or "event_date_required", operation_id)
        if result.status != "resolved" or not result.expression or result.expression not in before["content"]:
            raise EvidenceError("日期模块缺少原话支持")
        try:
            event_at = valid_event_at(result.event_at or "")
        except (ValueError, TypeError) as exc:
            raise EvidenceError("日期模块没有给出明确日期") from exc
        repaired = self.repo.update(
            owner,
            "fact",
            fact_id,
            dict(event_at=event_at, original_expression=result.expression, said_at=said_at.isoformat()),
            expected_revision=revision,
            operation_id=operation_id + ":date",
        )
        return self._record(owner, subject, before, repaired, operation_id)

    def _record(self, owner: str, subject: str, before: dict, repaired: dict, operation_id: str) -> dict:
        fact_id = before["id"]
        ident = "memory2_event_date_" + fingerprint([owner, operation_id])[:32]
        change = self.repo.put(
            owner,
            "proposal",
            ident,
            dict(
                kind=CHANGE_KIND,
                status="applied",
                before=before,
                fact_ids=[fact_id],
                source_refs=before["source_refs"],
                source_ids=self._sources(before),
                target_revision=repaired["revision"],
                prepared_at=self.clock.now().isoformat(),
            ),
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":change",
        )
        return dict(
            write_status="updated",
            code="memory2_event_date_repaired",
            fact_id=fact_id,
            revision=repaired["revision"],
            ids=[ident],
            context_revision=change["revision"],
        )

    @staticmethod
    def _sources(fact: dict) -> list[str]:
        return list(dict.fromkeys(ref["message_id"] for ref in fact["source_refs"]))

    def _gap(self, owner: str, subject: str, fact: dict, reason: str, operation_id: str) -> dict:
        ident = "memory2_event_gap_" + fingerprint([owner, fact["id"], fact["revision"]])[:32]
        try:
            gap = self.repo.get(owner, "knowledge_gap", ident, include_deleted=True)
        except ScopeError:
            gap = self.repo.put(
                owner,
                "knowledge_gap",
                ident,
                dict(
                    kind=GAP_KIND,
                    status="open",
                    fact_ids=[fact["id"]],
                    target_revision=fact["revision"],
                    source_refs=fact["source_refs"],
                    source_ids=self._sources(fact),
                    reason=reason,
                    question="这件事具体是哪一天发生的？",
                    prepared_at=self.clock.now().isoformat(),
                ),
                subject=subject,
                case_id=fact.get("case_id"),
                expected_revision=0,
                operation_id=operation_id + ":gap",
            )
        if self.repo.is_revoked(owner, "knowledge_gap", ident):
            raise EvidenceError("事件日期知识缺口已撤销")
        self.check_record(subject, fact, gap, GAP_KIND, "open")
        return dict(
            write_status="pending_confirmation",
            code="memory2_event_date_gap",
            fact_id=fact["id"],
            revision=fact["revision"],
            id=ident,
            kind="knowledge_gap",
            context_revision=gap["revision"],
        )

    @staticmethod
    def check_record(subject: str, fact: dict, record: dict, kind: str, status: str) -> None:
        if (
            record["subject_id"] != subject
            or record.get("kind") != kind
            or record["status"] != status
            or record.get("fact_ids") != [fact["id"]]
            or record.get("target_revision") != fact["revision"]
            or record.get("source_refs") != fact["source_refs"]
            or record.get("case_id") != fact.get("case_id")
        ):
            raise EvidenceError("原事件日期整理记录已失效")

    def _verify(self, owner: str, subject: str, fact_id: str, receipt: dict) -> None:
        fact = self.fact(owner, subject, fact_id)
        pending = receipt["write_status"] == "pending_confirmation"
        kind, ident = ("knowledge_gap", receipt["id"]) if pending else ("proposal", receipt["ids"][0])
        record = self.repo.get(owner, kind, ident)
        if self.repo.is_revoked(owner, kind, ident):
            raise EvidenceError("事件日期整理记录已撤销")
        self.check_record(subject, fact, record, GAP_KIND if pending else CHANGE_KIND, "open" if pending else "applied")
        if (
            fact["revision"] != receipt["revision"]
            or record["revision"] != receipt["context_revision"]
            or (bool(fact.get("event_at")) == pending)
        ):
            raise EvidenceError("原事件日期整理回执已失效")


def checked_event_gap(memory: MemoryService, owner: str, subject: str, record: dict) -> None:
    """The context reader must not ask an obsolete question about a later fact revision."""
    if len(record.get("fact_ids", [])) != 1 or memory.repo.is_revoked(owner, "knowledge_gap", record["id"]):
        raise EvidenceError("事件日期知识缺口已失效")
    service = MemoryEventTimeRepairService(memory)
    fact = service.fact(owner, subject, record["fact_ids"][0])
    service.check_record(subject, fact, record, GAP_KIND, "open")
    if fact.get("event_at"):
        raise EvidenceError("事件日期已补全，无需再次询问")

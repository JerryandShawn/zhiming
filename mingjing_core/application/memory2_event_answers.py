"""Apply an authenticated user's single-date answer to one selected memory knowledge gap."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.agent_tools_dates import valid_event_at
from mingjing_core.application.memory2_event_dates import GAP_KIND, MemoryEventTimeRepairService
from mingjing_core.application.memory2_fact_authority import statement_instant
from mingjing_core.application.memory2_proposals import approval_reference
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.policy import has_optout, hypothetical, mask_quoted
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock

ANSWER_CHANGE = "memory2_event_confirmation_undo"


class MemoryEventAnswerService:
    """The authenticated caller selects the gap; a model cannot supply authorization flags."""

    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo = memory, memory.repo
        self.repairs = MemoryEventTimeRepairService(memory, clock=clock)

    def confirm(
        self,
        owner: str,
        subject: str,
        gap_id: str,
        *,
        expected_revision: int,
        message_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("事件日期确认修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.action(owner, subject, message_id)
            payload = dict(
                subject=subject,
                id=gap_id,
                revision=expected_revision,
                message_id=message_id,
                action_revision=action["revision"],
            )
            self.repo.mutation_request(
                owner,
                "memory2_event_answer_action",
                message_id,
                dict(payload, operation_id=operation_id),
                lambda: {"status": "bound"},
            )
            receipt = self.repo.mutation_request(
                owner,
                "memory2_event_answer",
                operation_id,
                payload,
                partial(self._apply, owner, subject, gap_id, expected_revision, action, operation_id),
            )
            self.checked(owner, subject, receipt)
            return receipt

    def action(self, owner: str, subject: str, message_id: str) -> dict:
        action = self.memory.get_source(owner, message_id)
        verify_originals(self.memory, owner, subject, [approval_reference(action)])
        at = history_instant(action.get("at"))
        policy = action.get("policy", {})
        if (
            action.get("thread_id") != "life:" + subject
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or at is None
            or at > self.repairs.clock.now()
            or has_optout(action["content"])
            or hypothetical(action["content"], 0, len(action["content"]))
            or mask_quoted(action["content"]) != action["content"]
        ):
            raise EvidenceError("需要当前用户在长期线程明确确认日期")
        return action

    def _pending(self, owner: str, subject: str, gap_id: str, revision: int, action: dict) -> tuple[dict, dict]:
        gap = self.repo.get(owner, "knowledge_gap", gap_id)
        if gap["subject_id"] != subject:
            raise ScopeError("事件知识缺口不属于当前人物")
        if gap["revision"] != revision:
            raise RevisionConflict("事件知识缺口已再次修改")
        if len(gap.get("fact_ids", [])) != 1 or self.repo.is_revoked(owner, "knowledge_gap", gap_id):
            raise EvidenceError("事件知识缺口已失效")
        fact = self.repairs.fact(owner, subject, gap["fact_ids"][0])
        self.repairs.check_record(subject, fact, gap, GAP_KIND, "open")
        prepared = history_instant(gap.get("prepared_at") or gap.get("updated_at"))
        if (
            fact.get("event_at")
            or action["id"] in self.repairs._sources(fact)
            or action["created_at"] < gap["updated_at"]
            or prepared is None
            or history_instant(action["at"]) < prepared
            or history_instant(action["at"]) < statement_instant(self.memory, owner, fact)
        ):
            raise EvidenceError("确认须晚于知识缺口且不能覆盖已有日期")
        return gap, fact

    def _date(self, action: dict, fact: dict) -> tuple[str, str]:
        result = self.repairs.parser.resolve(
            action["content"],
            said_at=history_instant(action["at"]),
            timezone=fact["owner_timezone"],
        )
        if result.status != "resolved" or not result.expression or not result.event_at:
            raise EvidenceError("日期答复仍需要明确单点日期")
        expression = result.expression
        accepted = {expression, expression + "。", "这件事发生在" + expression, "这件事发生在" + expression + "。"}
        if action["content"].strip() not in accepted:
            raise EvidenceError("日期答复不能包含其他事项或未经确认的说法")
        return valid_event_at(result.event_at), expression

    def _apply(self, owner: str, subject: str, gap_id: str, revision: int, action: dict, operation_id: str) -> dict:
        gap, before = self._pending(owner, subject, gap_id, revision, action)
        event_at, expression = self._date(action, before)
        refs = [*before["source_refs"], approval_reference(action)]
        fact = self.repo.update(
            owner,
            "fact",
            before["id"],
            dict(
                event_at=event_at,
                source_refs=refs,
                date_confirmation_expression=expression,
                date_confirmation_at=action["at"],
                date_confirmation_message_id=action["id"],
            ),
            expected_revision=before["revision"],
            operation_id=operation_id + ":fact",
        )
        resolved = self.repo.update(
            owner,
            "knowledge_gap",
            gap_id,
            dict(
                status="resolved",
                target_revision=fact["revision"],
                source_refs=refs,
                source_ids=self.repairs._sources(fact),
                answer_message_id=action["id"],
            ),
            expected_revision=revision,
            operation_id=operation_id + ":resolve",
        )
        return self._record(owner, subject, before, gap, fact, resolved, operation_id)

    def _record(self, owner: str, subject: str, before: dict, gap: dict, fact: dict, resolved: dict, operation_id: str):
        change = self.repo.put(
            owner,
            "proposal",
            "memory2_event_answer_" + fingerprint([owner, operation_id])[:32],
            dict(
                kind=ANSWER_CHANGE,
                status="applied",
                before=before,
                gap_before=gap,
                gap_id=gap["id"],
                fact_ids=[fact["id"]],
                source_refs=fact["source_refs"],
                source_ids=self.repairs._sources(fact),
                target_revision=fact["revision"],
                gap_revision=resolved["revision"],
                confirmed_at=self.repairs.clock.now().isoformat(),
            ),
            subject=subject,
            case_id=fact.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":change",
        )
        return dict(
            write_status="updated",
            code="memory2_event_date_confirmed",
            fact_id=fact["id"],
            revision=fact["revision"],
            ids=[change["id"], gap["id"]],
            context_revision=change["revision"],
        )

    def checked(self, owner: str, subject: str, receipt: dict) -> tuple[dict, dict, dict]:
        fact = self.repairs.fact(owner, subject, receipt["fact_id"])
        change = self.repo.get(owner, "proposal", receipt["ids"][0])
        gap = self.repo.get(owner, "knowledge_gap", receipt["ids"][1])
        if (
            change.get("kind") != ANSWER_CHANGE
            or change["revision"] != receipt["context_revision"]
            or self.repo.is_revoked(owner, "proposal", change["id"])
            or self.repo.is_revoked(owner, "knowledge_gap", gap["id"])
            or gap["revision"] != change.get("gap_revision")
            or change.get("gap_id") != gap["id"]
            or fact["revision"] != receipt["revision"]
            or not fact.get("event_at")
        ):
            raise EvidenceError("原事件日期确认回执已失效")
        self.repairs.check_record(subject, fact, change, ANSWER_CHANGE, "applied")
        self.repairs.check_record(subject, fact, gap, GAP_KIND, "resolved")
        return change, fact, gap

"""Explicit choices consume the same P3 conflict proposal and literal save authority."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any, Literal

from mingjing_core.application.agent_tools_policy import KIND_MAP
from mingjing_core.application.memory2_conflicts import checked_conflict
from mingjing_core.application.memory2_fact_authority import (
    authorized_fact,
    statement_instant,
)
from mingjing_core.application.memory2_proposals import (
    MemoryProposalService,
    approval_reference,
    require_current_action,
)
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory2.contradictions import contradictory
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.repositories.postgres import PostgresRepository
    from mingjing_core.timekit.clock import Clock

USE_OLD = "以以前的说法为准，这条不保存"
USE_NEW = "以这次说法为准并保存"
REMEMBER = "，以后这类都记"
ACTIVE = frozenset({"active"})


def bind_action(
    repo: PostgresRepository, owner: str, subject: str, proposal_id: str, action: dict, operation: str
) -> None:
    # A current user click authorizes one specific operation, including keep-old.
    proposal = repo.get(owner, "proposal", proposal_id)
    instant = history_instant(action.get("at"))
    if action["created_at"] < proposal["created_at"]:
        raise EvidenceError("用户操作早于当前冲突提案")
    for ref in proposal.get("source_refs", []):
        source = repo.get(owner, "message", ref["message_id"])
        before = history_instant(source.get("at"))
        if instant is None or before is None or instant < before or action["created_at"] < source["created_at"]:
            raise EvidenceError("用户操作早于冲突原话或上次选择")
    repo.mutation_request(
        owner,
        "memory2_conflict_action",
        action["id"],
        {"subject": subject, "proposal_id": proposal_id, "operation": operation, "revision": action["revision"]},
        lambda: {"id": proposal_id, "kind": "proposal", "message_id": action["id"], "code": "conflict_action_bound"},
    )


def checked_resolution(memory: MemoryService, owner: str, subject: str, proposal: dict) -> tuple[dict, dict | None]:
    if proposal["subject_id"] != subject:
        raise ScopeError("冲突选择不属于当前人物")
    if proposal.get("proposal_type") != "memory_conflict" or proposal["status"] not in {"resolved_old", "resolved_new"}:
        raise EvidenceError("原冲突选择已失效")
    verify_originals(memory, owner, subject, proposal["source_refs"])
    old = authorized_fact(memory, owner, subject, proposal["target_fact_id"], statuses=ACTIVE)
    if old["revision"] != proposal["old_revision"] or old.get("case_id") != proposal.get("case_id"):
        raise RevisionConflict("选择后的旧记忆已再次变化")
    current = {row["id"] for row in memory.facts(owner, subject, [old["case_id"]] if old.get("case_id") else [])}
    if proposal["status"] == "resolved_old":
        if old["id"] not in current:
            raise EvidenceError("选择保留的旧记忆已不再有效")
        return old, None
    new = authorized_fact(memory, owner, subject, proposal["fact_id"], statuses=ACTIVE)
    if (
        new["revision"] != proposal["accepted_revision"]
        or new["id"] not in current
        or new.get("case_id") != old.get("case_id")
        or new.get("approval_consent_id") != proposal.get("consent_id")
        or new.get("supersedes") != old["id"]
        or old.get("superseded_by") != new["id"]
        or old.get("valid_to") != new.get("valid_from")
    ):
        raise RevisionConflict("选择后的新记忆或更新链已再次变化")
    return old, new


class MemoryConflictResolutionService:
    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.proposals = MemoryProposalService(memory)
        self.memory, self.repo, self.clock = self.proposals.memory, memory.repo, clock or get_clock()

    def resolve(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        *,
        expected_revision: int,
        message_id: str,
        choice: Literal["old", "new"],
        remember_category: bool = False,
        operation_id: str,
    ) -> dict[str, Any]:
        if (
            not isinstance(choice, str)
            or choice not in {"old", "new"}
            or type(remember_category) is not bool
            or type(expected_revision) is not int
            or expected_revision < 1
            or choice == "old"
            and remember_category
        ):
            raise EvidenceError("冲突选择参数无效")
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            at = history_instant(action.get("at"))
            if at is None or at > self.clock.now():
                raise EvidenceError("冲突选择的用户操作时间无效")
            command = USE_OLD if choice == "old" else USE_NEW + (REMEMBER if remember_category else "")
            require_current_action(action, command)
            bind_action(self.repo, owner, subject, proposal_id, action, operation_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_conflict_resolve",
                operation_id,
                {
                    "subject": subject,
                    "proposal_id": proposal_id,
                    "revision": expected_revision,
                    "message_id": message_id,
                    "choice": choice,
                    "remember_category": remember_category,
                },
                partial(
                    self._apply,
                    connection,
                    owner,
                    subject,
                    proposal_id,
                    expected_revision,
                    action,
                    choice,
                    remember_category,
                    operation_id,
                ),
            )
            self._verify_receipt(owner, subject, proposal_id, choice, receipt)
            return receipt

    def _verify_receipt(self, owner: str, subject: str, ident: str, choice: str, receipt: dict) -> None:
        proposal = self.repo.get(owner, "proposal", ident)
        old, new = checked_resolution(self.memory, owner, subject, proposal)
        if choice == "new":
            if new is None or new["id"] != receipt["fact_id"] or new["revision"] != receipt["revision"]:
                raise EvidenceError("原冲突更新回执已失效")
        elif new is not None or proposal["revision"] != receipt["revision"] or old["id"] != receipt["fact_id"]:
            raise EvidenceError("原保留旧值回执已失效")

    def _apply(
        self,
        connection: Any,
        owner: str,
        subject: str,
        ident: str,
        revision: int,
        action: dict,
        choice: str,
        remember: bool,
        operation_id: str,
    ) -> dict[str, Any]:
        proposal = self.proposals._pending(owner, subject, ident, revision, allow_conflict=True)
        if proposal.get("proposal_type") != "memory_conflict":
            raise EvidenceError("此提案不是冲突选择")
        old = checked_conflict(self.memory, owner, subject, proposal)
        if choice == "old":
            return self._keep(owner, subject, proposal, old, action, operation_id)
        self._unique_target(owner, subject, proposal, old)
        return self._replace(connection, owner, subject, proposal, old, action, remember, operation_id)

    def _unique_target(self, owner: str, subject: str, proposal: dict, old: dict) -> None:
        incoming = proposal["source_refs"][0]["quote"]
        cases = [old["case_id"]] if old.get("case_id") else []
        matches = [
            row
            for row in self.memory.facts(owner, subject, cases)
            if row.get("case_id") == old.get("case_id")
            and row.get("kind") == old.get("kind")
            and contradictory(row, incoming, proposal.get("conflict_slot"))
        ]
        if {row["id"] for row in matches} != {old["id"]}:
            raise EvidenceError("有多条同主题旧记忆，需要先明确更正范围")

    def _keep(self, owner: str, subject: str, proposal: dict, old: dict, action: dict, operation_id: str) -> dict:
        row = self.repo.update(
            owner,
            "proposal",
            proposal["id"],
            {
                "status": "resolved_old",
                "selection": "old",
                "proposal_before": proposal,
                "old_revision": old["revision"],
                "source_refs": [*proposal["source_refs"], approval_reference(action)],
            },
            expected_revision=proposal["revision"],
            operation_id=operation_id + ":keep",
        )
        return {
            "write_status": "stopped",
            "id": row["id"],
            "kind": "proposal",
            "revision": row["revision"],
            "fact_id": old["id"],
            "code": "memory2_conflict_kept_old",
        }

    def _save_new(
        self, owner: str, subject: str, proposal: dict, action: dict, operation_id: str
    ) -> tuple[dict, dict, tuple]:
        proof, source, categories = self.proposals._consent(owner, subject, proposal, action, operation_id)
        ref = proposal["source_refs"][0]
        row = self.memory.save_fact(
            owner,
            subject,
            source["id"],
            ref["quote"],
            KIND_MAP.get(proposal["kind"], proposal["kind"]),
            case_id=proposal.get("case_id"),
            authorization_id=proof["id"],
            operation_id=operation_id + ":fact",
        )
        if row.get("write_status") != "saved":
            raise EvidenceError("已选择的新说法尚未满足保存授权")
        row = self.proposals._decorate(owner, proposal, action, source, row, proof["id"], operation_id)
        return row, proof, categories

    def _close_at(self, owner: str, old: dict, new: dict) -> str:
        before, after = statement_instant(self.memory, owner, old), statement_instant(self.memory, owner, new)
        if before > after or after > self.clock.now() or old.get("superseded_by"):
            raise EvidenceError("新说法时间无效或旧值已被更新")
        if before == after:
            previous = self.memory.get_source(
                owner, next(ref["message_id"] for ref in old["source_refs"] if ref["quote"] == old["content"])
            )
            incoming = self.memory.get_source(
                owner, next(ref["message_id"] for ref in new["source_refs"] if ref["quote"] == new["content"])
            )
            if (incoming["created_at"], incoming["id"]) <= (previous["created_at"], previous["id"]):
                raise EvidenceError("同刻原话的先后顺序无法确认")
        return after.isoformat()

    def _replace(
        self,
        connection: Any,
        owner: str,
        subject: str,
        proposal: dict,
        old: dict,
        action: dict,
        remember: bool,
        operation_id: str,
    ) -> dict[str, Any]:
        new, proof, categories = self._save_new(owner, subject, proposal, action, operation_id)
        if remember and not categories:
            raise EvidenceError("普通偏好不需要新增敏感类别授权")
        closed_at = self._close_at(owner, old, new)
        before_settings = (
            self.proposals._grant(connection, owner, subject, categories, proof["id"]) if remember else None
        )
        after_settings = self.proposals._memory_settings(owner, subject) if remember else None
        previous, current = self._close_pair(owner, old, new, closed_at, operation_id)
        self.repo.update(
            owner,
            "proposal",
            proposal["id"],
            {
                "status": "resolved_new",
                "selection": "new",
                "proposal_before": proposal,
                "old_before": old,
                "old_revision": previous["revision"],
                "fact_id": current["id"],
                "accepted_revision": current["revision"],
                "consent_id": proof["id"],
                "fact_ids": [old["id"], current["id"]],
                "source_refs": [*proposal["source_refs"], approval_reference(action)],
                "memory_settings_before": before_settings,
                "memory_settings_after": after_settings,
            },
            expected_revision=proposal["revision"],
            operation_id=operation_id + ":resolved",
        )
        return {
            "write_status": "updated",
            "id": current["id"],
            "fact_id": current["id"],
            "kind": "fact",
            "revision": current["revision"],
            "ids": [proposal["id"]],
            "code": "memory2_conflict_resolved",
        }

    def _close_pair(self, owner: str, old: dict, new: dict, closed_at: str, operation_id: str) -> tuple[dict, dict]:
        previous = self.repo.update(
            owner,
            "fact",
            old["id"],
            {"valid_to": closed_at, "superseded_by": new["id"]},
            expected_revision=old["revision"],
            operation_id=operation_id + ":close",
        )
        current = self.repo.update(
            owner,
            "fact",
            new["id"],
            {"valid_from": closed_at, "supersedes": old["id"]},
            expected_revision=new["revision"],
            operation_id=operation_id + ":open",
        )
        return previous, current

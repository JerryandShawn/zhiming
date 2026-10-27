"""Confirm a sensitive P3 proposal and replace one current slot in one transaction."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_fact_authority import authorized_fact
from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.application.memory2_slots import MemorySlotUpdateService
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

ACTIVE = frozenset({"active"})


class MemoryConfirmedSlotService:
    """Application entry point only; runtime tools and their commit gates remain separate."""

    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo
        self.proposals = MemoryProposalService(memory)
        self.slots = MemorySlotUpdateService(memory)

    def accept(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        old_id: str,
        *,
        slot: str,
        expected_proposal_revision: int,
        expected_old_revision: int,
        message_id: str,
        remember_category: bool,
        operation_id: str,
    ) -> dict[str, Any]:
        payload = dict(
            subject=subject,
            proposal_id=proposal_id,
            old_id=old_id,
            slot=slot,
            proposal_revision=expected_proposal_revision,
            old_revision=expected_old_revision,
            message_id=message_id,
            remember_category=remember_category,
        )
        if type(remember_category) is not bool or any(
            type(rev) is not int or rev < 1 for rev in (expected_proposal_revision, expected_old_revision)
        ):
            raise EvidenceError("确认更新参数无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_confirmed_slot",
                operation_id,
                payload,
                partial(self._apply, owner, subject, payload, operation_id),
            )
            self.checked(owner, subject, receipt)
            return receipt

    def _apply(self, owner: str, subject: str, args: dict, operation_id: str) -> dict:
        # A newly granted category must not retroactively legitimize an old row.
        old = authorized_fact(self.memory, owner, subject, args["old_id"], statuses=ACTIVE)
        if old["revision"] != args["old_revision"]:
            raise RevisionConflict("原记忆已变化")
        proposal = self.repo.get(owner, "proposal", args["proposal_id"])
        action = self.memory.get_source(owner, args["message_id"])
        at = history_instant(action.get("at"))
        if at is None or at > get_clock().now() or action["created_at"] < proposal["created_at"]:
            raise EvidenceError("确认操作早于当前提案或时间无效")
        accepted = self.proposals.accept(
            owner,
            subject,
            args["proposal_id"],
            expected_revision=args["proposal_revision"],
            message_id=args["message_id"],
            remember_category=args["remember_category"],
            operation_id=operation_id + ":accept",
        )
        updated = self.slots.update(
            owner,
            subject,
            old["id"],
            accepted["fact_id"],
            slot=args["slot"],
            expected_old_revision=old["revision"],
            expected_new_revision=accepted["revision"],
            operation_id=operation_id + ":update",
        )
        proposal = self.repo.get(owner, "proposal", args["proposal_id"])
        change = self.repo.get(owner, "proposal", updated["ids"][0])
        linked = self.repo.update(
            owner,
            "proposal",
            change["id"],
            {
                "confirmation_id": proposal["id"],
                "confirmation_revision": proposal["revision"],
                "consent_id": proposal["consent_id"],
            },
            expected_revision=change["revision"],
            operation_id=operation_id + ":link",
        )
        return dict(
            updated,
            code="memory2_confirmed_slot",
            context_revision=linked["revision"],
            ids=[change["id"], proposal["id"]],
        )

    def checked(self, owner: str, subject: str, receipt: dict) -> tuple[dict, dict]:
        change = self.repo.get(owner, "proposal", receipt["ids"][0])
        if change["subject_id"] != subject or change.get("confirmation_id") != receipt["ids"][1]:
            raise EvidenceError("确认更新的来源绑定无效")
        self.slots._verify_receipt(owner, subject, change["old_before"]["id"], receipt["fact_id"], receipt)
        proposal = self.repo.get(owner, "proposal", change["confirmation_id"])
        if (
            change["revision"] != receipt["context_revision"]
            or proposal["revision"] != change["confirmation_revision"]
            or proposal["status"] != "accepted"
            or proposal.get("fact_id") != receipt["fact_id"]
            or proposal.get("consent_id") != change.get("consent_id")
            or proposal.get("accepted_revision") != change["new_before"]["revision"]
            or not isinstance(proposal.get("proposal_before"), dict)
        ):
            raise EvidenceError("原记忆确认或更新已变化")
        return change, proposal

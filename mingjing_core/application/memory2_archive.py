"""Source-checked dated-event archival in the real memory repository, without deletion."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_consent import consent_live
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.policy import has_optout
from mingjing_core.memory2.expiration import archive_deadline
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService
    from mingjing_core.timekit.clock import Clock


class MemoryArchiveService:
    """Caller supplies authenticated owner and the exact candidate revision.

    This is a local application service, not a background scheduler or tool receipt.
    Undo snapshots use the existing proposal cascade so forgotten data cannot survive.
    """

    def __init__(self, memory: MemoryService, *, clock: Clock | None = None) -> None:
        self.memory, self.repo, self.clock = memory, memory.repo, clock or get_clock()

    def archive(
        self,
        owner: str,
        subject: str,
        fact_id: str,
        *,
        expected_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise EvidenceError("归档记忆修订无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            self._check_fact(owner, subject, fact_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_archive",
                operation_id,
                {"subject": subject, "fact_id": fact_id, "revision": expected_revision},
                partial(
                    self._apply,
                    owner,
                    subject,
                    fact_id,
                    expected_revision,
                    operation_id,
                ),
            )
            fact = self._check_fact(owner, subject, fact_id)
            change = self.repo.get(owner, "proposal", receipt["ids"][0])
            if (
                fact["status"] != "archived"
                or fact["revision"] != receipt["revision"]
                or change["status"] != "applied"
                or change.get("kind") != "memory2_archive_undo"
            ):
                raise EvidenceError("原记忆归档回执已失效")
            return receipt

    def _check_fact(self, owner: str, subject: str, fact_id: str) -> dict[str, Any]:
        fact = self.repo.get(owner, "fact", fact_id, include_deleted=True)
        if fact["subject_id"] != subject:
            raise ScopeError("归档记忆不属于当前人物")
        if (
            fact["status"] not in {"active", "archived"}
            or fact.get("consent") != "granted"
            or fact.get("assertion_status") != "user_asserted"
            or self.repo.is_revoked(owner, "fact", fact_id)
        ):
            raise EvidenceError("归档记忆已失效或未获授权")
        verify_originals(self.memory, owner, subject, fact.get("source_refs", []))
        proofs = fact.get("category_consent_ids", [])
        if not isinstance(proofs, list) or any(not isinstance(ident, str) for ident in proofs):
            raise EvidenceError("记忆归档授权结构无效")
        if fact.get("approval_consent_id"):
            proofs = [*proofs, fact["approval_consent_id"]]
        for ident in proofs:
            proof = self.repo.get(owner, "consent", ident)
            if not consent_live(self.memory, owner, subject, proof):
                raise EvidenceError("记忆归档授权已失效")
        for ref in fact["source_refs"]:
            source = self.memory.get_source(owner, ref["message_id"])
            policy = source.get("policy", {})
            if (
                policy.get("origin") != "current_user"
                or policy.get("run_context") is not True
                or source.get("thread_id") != "life:" + subject
                or has_optout(source["content"])
            ):
                raise EvidenceError("归档来源不属于已授权长期记忆")
        return fact

    def _apply(
        self,
        owner: str,
        subject: str,
        fact_id: str,
        expected_revision: int,
        operation_id: str,
    ) -> dict[str, Any]:
        before = self._check_fact(owner, subject, fact_id)
        if before["revision"] != expected_revision:
            raise RevisionConflict("归档前记忆已变化")
        now = self.clock.now()
        deadline = archive_deadline(before)
        said_at = history_instant(before.get("said_at") or before.get("valid_from"))
        if before["status"] != "active" or deadline is None or deadline > now or said_at is None or said_at > now:
            raise EvidenceError("记忆尚未到期或日期需要确认")
        archived = self.repo.update(
            owner,
            "fact",
            fact_id,
            {
                "status": "archived",
                "archived_at": now.isoformat(),
                "archive_deadline": deadline.isoformat(),
            },
            expected_revision=expected_revision,
            operation_id=operation_id + ":archive",
        )
        # Expiry is not withdrawal: preserve historical answers and user edits.
        # Fact revision guards invalidate old snapshots; current projections already
        # require every referenced fact to remain in memory.facts().
        change_id = self._record_change(owner, subject, before, archived, operation_id)
        return {
            "write_status": "archived",
            "fact_id": fact_id,
            "revision": archived["revision"],
            "ids": [change_id],
        }

    def _record_change(
        self, owner: str, subject: str, before: dict[str, Any], archived: dict[str, Any], operation_id: str
    ) -> str:
        change_id = "memory2_archive_" + fingerprint([owner, operation_id])[:32]
        self.repo.put(
            owner,
            "proposal",
            change_id,
            {
                "kind": "memory2_archive_undo",
                "status": "applied",
                "before": before,
                "fact_ids": [before["id"]],
                "source_refs": before["source_refs"],
                "source_ids": list(dict.fromkeys(ref["message_id"] for ref in before["source_refs"])),
                "target_revision": archived["revision"],
            },
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=0,
            operation_id=operation_id + ":archive-change",
        )
        return change_id

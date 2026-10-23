"""Explicit acceptance and exact undo for P3 profile proposals; no automatic user facts."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_profile_reflection import checked_profile, checked_profile_facts
from mingjing_core.application.memory2_proposals import approval_reference, require_current_action
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService

ACCEPT_PROFILE = "请采用这条画像建议"
DISMISS_PROFILE = "忽略这条画像建议"
UNDO_PROFILE = "撤销这次画像确认"


class ProfileProposalService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

    def act(
        self,
        owner: str,
        subject: str,
        proposal_id: str,
        *,
        expected_revision: int,
        message_id: str,
        action: str,
        operation_id: str,
    ) -> dict[str, Any]:
        commands = {"accept": ACCEPT_PROFILE, "dismiss": DISMISS_PROFILE, "undo": UNDO_PROFILE}
        if (
            not isinstance(action, str)
            or action not in commands
            or type(expected_revision) is not int
            or expected_revision < 1
        ):
            raise EvidenceError("画像确认操作无效")
        with self.repo.transaction(owner):
            proposal = self.repo.get(owner, "proposal", proposal_id, include_deleted=True)
            if proposal["subject_id"] != subject:
                raise ScopeError("画像提案不属于当前人物")
            if proposal.get("proposal_type") != "profile_doc" and not (
                action == "dismiss" and proposal["status"] == "deleted"
            ):
                raise EvidenceError("此提案不是画像建议")
            original = self.memory.get_source(owner, message_id)
            self._action(owner, subject, proposal, original, commands[action], operation_id)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_profile_action",
                operation_id,
                {
                    "subject": subject,
                    "proposal_id": proposal_id,
                    "revision": expected_revision,
                    "message_id": message_id,
                    "action": action,
                },
                partial(self._apply, owner, subject, proposal_id, expected_revision, original, action, operation_id),
            )
            self._verify(owner, subject, proposal_id, action, receipt)
            return receipt

    def _action(self, owner: str, subject: str, proposal: dict, original: dict, command: str, operation: str) -> None:
        require_current_action(original, command)
        verify_originals(self.memory, owner, subject, [approval_reference(original)])
        at = history_instant(original.get("at"))
        if at is None or at > get_clock().now() or original["created_at"] < proposal["created_at"]:
            raise EvidenceError("画像操作时间无效")
        if command != UNDO_PROFILE and proposal["status"] == "pending" and "prepared_at" in proposal:
            prepared = history_instant(proposal["prepared_at"])
            if prepared is None or at < prepared:
                raise EvidenceError("画像操作必须晚于本次建议准备")
        for ref in proposal.get("source_refs", []):
            source = self.memory.get_source(owner, ref["message_id"])
            before = history_instant(source.get("at"))
            if before is None or at < before or original["created_at"] < source["created_at"]:
                raise EvidenceError("画像操作必须晚于其来源")
        self.repo.mutation_request(
            owner,
            "memory2_profile_action_binding",
            original["id"],
            {"proposal_id": proposal["id"], "operation": operation, "revision": original["revision"]},
            lambda: {"id": proposal["id"], "kind": "proposal", "message_id": original["id"]},
        )

    def _checked(self, owner: str, subject: str, proposal: dict, revision: int, status: str) -> None:
        if proposal["revision"] != revision:
            raise RevisionConflict("画像提案已经变化")
        if proposal["status"] != status:
            raise EvidenceError("画像提案状态不允许此操作")
        verify_originals(self.memory, owner, subject, proposal["source_refs"])
        checked_profile_facts(self.memory, owner, subject, proposal["fact_versions"])

    def _apply(
        self, owner: str, subject: str, ident: str, revision: int, original: dict, action: str, operation: str
    ) -> dict:
        proposal = self.repo.get(owner, "proposal", ident)
        self._checked(owner, subject, proposal, revision, "accepted" if action == "undo" else "pending")
        if action == "undo":
            return self._undo(owner, subject, proposal, operation)
        if action == "dismiss":
            row = self.repo.delete(
                owner, "proposal", ident, expected_revision=revision, operation_id=operation + ":dismiss"
            )
            return {"write_status": "stopped", "id": ident, "kind": "proposal", "revision": row["revision"]}
        return self._accept(owner, subject, proposal, original, operation)

    def _accept(self, owner: str, subject: str, proposal: dict, original: dict, operation: str) -> dict:
        before = checked_profile(self.memory, owner, subject, proposal["item_id"]) if proposal["item_id"] else None
        if before and before["revision"] != proposal["target_revision"]:
            raise RevisionConflict("原画像条目已被用户修改")
        ident = before["id"] if before else "profile_" + fingerprint([owner, proposal["id"], original["id"]])[:32]
        facts = checked_profile_facts(self.memory, owner, subject, proposal["input_fact_versions"])
        refs = [ref for row in facts for ref in row["source_refs"]] + [approval_reference(original)]
        row = self.repo.put(
            owner,
            "profile_doc",
            ident,
            {
                **(before or {}),
                "status": "active",
                "section": proposal["section"],
                "text": proposal["text"],
                "fact_ids": list(proposal["input_fact_versions"]),
                "fact_versions": proposal["input_fact_versions"],
                "source_refs": refs,
                "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
                "confidence": proposal["confidence"],
                "inferred": True,
                "assertion_status": "derived",
                "confirmed_by_user": True,
                "pinned": before.get("pinned", False) if before else False,
                "edited_by_user": before.get("edited_by_user", False) if before else False,
            },
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=proposal["target_revision"],
            operation_id=operation + ":profile",
        )
        self.repo.update(
            owner,
            "proposal",
            proposal["id"],
            {
                "status": "accepted",
                "item_id": ident,
                "accepted_revision": row["revision"],
                "profile_before": before,
                "proposal_before": proposal,
                "source_refs": [*proposal["source_refs"], approval_reference(original)],
            },
            expected_revision=proposal["revision"],
            operation_id=operation + ":accepted",
        )
        return {
            "write_status": "saved",
            "id": ident,
            "kind": "profile_doc",
            "revision": row["revision"],
            "ids": [proposal["id"]],
            "code": "memory2_profile_confirmed",
        }

    def _undo(self, owner: str, subject: str, proposal: dict, operation: str) -> dict:
        item = checked_profile(self.memory, owner, subject, proposal["item_id"])
        if item["revision"] != proposal["accepted_revision"]:
            raise RevisionConflict("确认后的画像已被再次修改")
        before = proposal["profile_before"]
        if before:
            restored = self.repo.put(
                owner,
                "profile_doc",
                item["id"],
                before,
                subject=subject,
                case_id=item.get("case_id"),
                expected_revision=item["revision"],
                operation_id=operation + ":restore-profile",
            )
        else:
            restored = self.repo.delete(
                owner,
                "profile_doc",
                item["id"],
                expected_revision=item["revision"],
                operation_id=operation + ":remove-profile",
            )
        pending = dict(proposal["proposal_before"])
        pending["prepared_at"] = get_clock().now().isoformat()
        if before:
            pending["target_revision"] = restored["revision"]
        row = self.repo.put(
            owner,
            "proposal",
            proposal["id"],
            pending,
            subject=subject,
            case_id=proposal.get("case_id"),
            expected_revision=proposal["revision"],
            operation_id=operation + ":restore-proposal",
        )
        self.repo.invalidate_derived(owner, [], [], recomputable=True, seed_entities=[("profile_doc", item["id"])])
        return {
            "write_status": "stopped",
            "id": row["id"],
            "kind": "proposal",
            "revision": row["revision"],
            "ids": [item["id"]],
            "code": "memory2_profile_undo",
        }

    def _verify(self, owner: str, subject: str, ident: str, action: str, receipt: dict) -> None:
        proposal = self.repo.get(owner, "proposal", ident, include_deleted=True)
        expected = {"accept": "accepted", "dismiss": "deleted", "undo": "pending"}[action]
        if proposal["status"] != expected:
            raise EvidenceError("原画像操作已撤销或失效")
        if action == "accept":
            item = checked_profile(self.memory, owner, subject, receipt["id"])
            if item["revision"] != receipt["revision"]:
                raise EvidenceError("原画像确认回执已失效")
        elif proposal["revision"] != receipt["revision"]:
            raise EvidenceError("原画像操作版本已变化")
        if action == "undo":
            verify_originals(self.memory, owner, subject, proposal["source_refs"])
            checked_profile_facts(self.memory, owner, subject, proposal["fact_versions"])
            if proposal.get("item_id"):
                item = checked_profile(self.memory, owner, subject, proposal["item_id"])
                if item["revision"] != proposal["target_revision"]:
                    raise EvidenceError("原画像撤销回执已失效")

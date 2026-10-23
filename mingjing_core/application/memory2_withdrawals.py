"""Authenticated selected-item withdrawal; deletion never reconstructs private snapshots."""

from __future__ import annotations

import re
from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.application.memory2_proposals import approval_reference
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


class MemoryWithdrawalService:
    """A trusted route binds the selected id; model-generated flags cannot authorize it."""

    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

    def withdraw_fact(
        self, owner: str, subject: str, fact_id: str, *, expected_revision: int, message_id: str, operation_id: str
    ) -> dict[str, Any]:
        return self._withdraw(owner, subject, "fact", fact_id, expected_revision, message_id, operation_id)

    def delete_source(
        self, owner: str, subject: str, source_id: str, *, expected_revision: int, message_id: str, operation_id: str
    ) -> dict[str, Any]:
        return self._withdraw(owner, subject, "message", source_id, expected_revision, message_id, operation_id)

    def _withdraw(
        self, owner: str, subject: str, kind: str, ident: str, revision: int, message_id: str, operation_id: str
    ) -> dict[str, Any]:
        if type(revision) is not int or revision < 1 or not operation_id:
            raise EvidenceError("撤销需要当前版本及稳定操作标识")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            verify_originals(self.memory, owner, subject, [approval_reference(action)])
            content = action["content"]
            command = (
                content == "删除这条来源消息"
                if kind == "message"
                else bool(re.fullmatch(r"撤销这条[^。？！!?\n]{0,30}记忆", content))
            )
            if (
                not command
                or action.get("policy", {}).get("origin") != "current_user"
                or action.get("policy", {}).get("run_context") is not True
            ):
                raise EvidenceError("需要当前用户明确撤销所选记忆或来源")
            if kind == "message" and ident == message_id:
                raise EvidenceError("撤销命令不能同时成为被删除的来源")
            receipt = self.repo.mutation_request(
                owner,
                "memory2_withdraw_" + kind,
                operation_id,
                {"subject": subject, "id": ident, "revision": revision, "message_id": message_id},
                partial(self._bound_apply, owner, subject, kind, ident, revision, action, operation_id),
            )
            target = self.repo.get(owner, kind, ident, include_deleted=True)
            if target["status"] != "deleted" or not self.repo.is_revoked(owner, kind, ident):
                raise EvidenceError("原删除结果已变化")
            return receipt

    def _bound_apply(
        self, owner: str, subject: str, kind: str, ident: str, revision: int, action: dict[str, Any], operation_id: str
    ) -> dict[str, Any]:
        # One generic button sentence must never authorize multiple selected items.
        return self.repo.mutation_request(
            owner,
            "memory2_withdraw_action",
            action["id"],
            {"subject": subject, "kind": kind, "id": ident, "revision": revision, "operation_id": operation_id},
            partial(self._apply, owner, subject, kind, ident, revision, action),
        )

    def _apply(
        self, owner: str, subject: str, kind: str, ident: str, revision: int, action: dict[str, Any]
    ) -> dict[str, Any]:
        target = self.repo.get(owner, kind, ident, include_deleted=True)
        if (
            target["subject_id"] != subject
            or target.get("case_id")
            and target["case_id"] not in action.get("case_ids", [])
        ):
            raise ScopeError("所选记忆或来源不属于当前人物与事项")
        if target["revision"] != revision:
            raise RevisionConflict("所选记忆或来源已经变化")
        self._chronology(owner, kind, target, action)
        if kind == "fact":
            row = self.memory.retire_fact(owner, ident, expected_revision=revision)
            affected = row.get("affected_fact_ids", [ident])
        else:
            affected = self._delete_source(owner, ident, revision)
        row = self.repo.get(owner, kind, ident, include_deleted=True)
        return {
            "write_status": "deleted",
            "id": ident,
            "kind": kind,
            "revision": row["revision"],
            "affected_ids": affected,
            "code": "memory2_selected_deleted",
        }

    def _chronology(self, owner: str, kind: str, target: dict[str, Any], action: dict[str, Any]) -> None:
        when = history_instant(action.get("at"))
        refs = target.get("source_refs", []) if kind == "fact" else [{"message_id": target["id"]}]
        if when is None or when > get_clock().now() or not refs:
            raise EvidenceError("撤销命令或原话时间无法确认")
        for ref in refs:
            if ref["message_id"] == action["id"]:
                raise EvidenceError("撤销命令不能成为目标的原始依据")
            source = self.repo.get(owner, "message", ref["message_id"], include_deleted=True)
            before = history_instant(source.get("at"))
            if source["subject_id"] != target["subject_id"] or before is None or when < before:
                raise EvidenceError("撤销命令必须晚于所选原话")

    def _delete_source(self, owner: str, ident: str, revision: int) -> list[str]:
        selected = [
            f["id"]
            for f in self.repo.list(owner, "fact")
            if any(ref.get("message_id") == ident for ref in f.get("source_refs", []))
        ]
        for fact_id in selected:
            current = self.repo.get(owner, "fact", fact_id, include_deleted=True)
            if current["status"] != "deleted":
                self.memory.retire_fact(owner, fact_id, expected_revision=current["revision"])
        self.repo.delete(owner, "message", ident, expected_revision=revision)
        self.repo.invalidate_derived(owner, selected, [ident])
        if self.memory.on_revoke:
            self.memory.on_revoke(owner, selected, [ident])
        return selected

"""Owner-authenticated undo service; transport wiring remains with the mainline."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.private import require_persistent_source

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


def verify_originals(memory: MemoryService, owner: str, subject: str, refs: list[dict[str, Any]]) -> None:
    if not refs:
        raise EvidenceError("撤销缺少原始来源")
    spans = [row["metadata"] for row in memory.repo.revocations(owner) if row["kind"] == "source_span"]
    for ref in refs:
        if (
            not isinstance(ref, dict)
            or not isinstance(ref.get("message_id"), str)
            or type(ref.get("version")) is not int
            or type(ref.get("start")) is not int
            or type(ref.get("end")) is not int
            or not isinstance(ref.get("quote"), str)
        ):
            raise EvidenceError("原始来源结构无效")
        source = memory.get_source(owner, ref["message_id"])
        require_persistent_source(source)
        if (
            source["subject_id"] != subject
            or source["status"] != "active"
            or source.get("role") != "user"
            or source["revision"] != ref["version"]
            or memory.repo.is_revoked(owner, "message", source["id"])
            or not 0 <= ref["start"] < ref["end"] <= len(source["content"])
            or source["content"][ref["start"] : ref["end"]] != ref["quote"]
        ):
            raise EvidenceError("原始来源已变化，不能撤销复活")
        for span in spans:
            if span.get("message_id") == source["id"] and max(ref["start"], span["start"]) < min(
                ref["end"], span["end"]
            ):
                raise EvidenceError("原话区间已撤销，不能恢复")


class MemoryMergeUndoService:
    """Caller supplies an authenticated owner and an explicit user undo message."""

    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

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
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            action = self.memory.get_source(owner, message_id)
            require_persistent_source(action)
            if (
                action["subject_id"] != subject
                or action["status"] != "active"
                or action.get("role") != "user"
                or action.get("policy", {}).get("origin") != "current_user"
                or action.get("policy", {}).get("run_context") is not True
                or action["content"].strip() not in {"撤销这次记忆合并", "撤销这次记忆变更"}
            ):
                raise EvidenceError("需要当前用户明确撤销指定记忆变更")
            verify_originals(
                self.memory,
                owner,
                subject,
                [
                    {
                        "message_id": action["id"],
                        "version": action["revision"],
                        "start": 0,
                        "end": len(action["content"]),
                        "quote": action["content"],
                    }
                ],
            )
            payload = {
                "subject": subject,
                "change_id": change_id,
                "revision": expected_revision,
                "message_id": message_id,
            }
            receipt = self.repo.mutation_request(
                owner,
                "memory2_merge_undo",
                operation_id,
                payload,
                partial(self._apply, owner, subject, change_id, expected_revision, operation_id),
            )
            restored = self.repo.get(owner, "fact", receipt["fact_id"], include_deleted=True)
            if restored["status"] != "active" or self.repo.is_revoked(owner, "fact", restored["id"]):
                raise EvidenceError("原撤销结果已失效")
            verify_originals(self.memory, owner, subject, restored["source_refs"])
            return receipt

    def _apply(
        self, owner: str, subject: str, change_id: str, expected_revision: int, operation_id: str
    ) -> dict[str, Any]:
        change = self.repo.get(owner, "proposal", change_id)
        if change["subject_id"] != subject:
            raise ScopeError("记忆变更不属于当前人物")
        if change["revision"] != expected_revision:
            raise RevisionConflict("记忆变更已变化")
        if change.get("kind") != "memory2_merge_undo" or change["status"] != "applied":
            raise EvidenceError("此变更不能撤销")
        verify_originals(self.memory, owner, subject, change["source_refs"])
        target = self.repo.get(owner, "fact", change["target_fact_id"])
        incoming = self.repo.get(owner, "fact", change["incoming_fact_id"])
        if target["revision"] != change["target_revision"] or incoming["revision"] != change["incoming_revision"]:
            raise RevisionConflict("合并后的记忆已被再次修改")
        if (
            target["status"] != "active"
            or incoming["status"] != "merged"
            or incoming.get("merged_into") != target["id"]
        ):
            raise EvidenceError("合并状态已失效")
        before = change["before"]
        restored = self.repo.put(
            owner,
            "fact",
            target["id"],
            before,
            subject=subject,
            case_id=before.get("case_id"),
            expected_revision=target["revision"],
            operation_id=operation_id + ":restore",
        )
        self.repo.update(
            owner,
            "fact",
            incoming["id"],
            {"status": "retired"},
            expected_revision=incoming["revision"],
            operation_id=operation_id + ":retire-input",
        )
        self.repo.invalidate_derived(owner, [target["id"], incoming["id"]], [], recomputable=True)
        return {
            "write_status": "saved",
            "code": "memory2_undo",
            "fact_id": target["id"],
            "revision": restored["revision"],
        }

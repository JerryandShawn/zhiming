"""Authenticated clicks become source-bound native memory actions, never model consent."""

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_archive_undo import MemoryArchiveUndoService
from mingjing_core.application.memory2_confirmed_slots_undo import MemoryConfirmedSlotUndoService
from mingjing_core.application.memory2_conflict_resolution import REMEMBER, USE_NEW, USE_OLD
from mingjing_core.application.memory2_conflict_resolution_undo import MemoryConflictUndoService
from mingjing_core.application.memory2_profile_proposals import ProfileProposalService
from mingjing_core.application.memory2_proposal_undo import MemoryProposalUndoService
from mingjing_core.application.memory2_proposals import SAVE_CATEGORY, SAVE_ONCE, MemoryProposalService
from mingjing_core.application.memory2_slots_undo import MemorySlotUndoService
from mingjing_core.application.memory2_undo import MemoryMergeUndoService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock

UNDO = {
    "slot": (MemorySlotUndoService, "撤销这次记忆更新"),
    "confirmed_slot": (MemoryConfirmedSlotUndoService, "撤销这次记忆更新和确认"),
    "merge": (MemoryMergeUndoService, "撤销这次记忆合并"),
    "archive": (MemoryArchiveUndoService, "撤销这次记忆归档"),
}


class MemoryWebActions:
    def __init__(self, repo):
        self.repo, self.memory = repo, V4FactMemory(repo)

    def _handler(self, family, action, remember, choice):
        if choice is not None and (family != "conflict" or action != "confirm"):
            raise EvidenceError("当前提案不接受冲突选择")
        if family == "conflict" and action == "confirm":
            if choice not in {"old", "new"} or choice == "old" and remember:
                raise EvidenceError("需要明确选择旧说法或新说法")
            command = USE_OLD if choice == "old" else USE_NEW + (REMEMBER if remember else "")
            return command, lambda *args, **kwargs: MemoryProposalService(self.memory).resolve_conflict(
                *args, **kwargs, choice=choice, remember_category=remember
            )
        if family == "conflict" and action == "undo":
            return "撤销这次冲突选择", MemoryConflictUndoService(self.memory).undo
        if family == "profile":
            if remember:
                raise EvidenceError("画像建议不能授权自动保存同类记忆")
            mapped = {"confirm": "accept", "ignore": "dismiss", "undo": "undo"}[action]
            commands = {"confirm": "请采用这条画像建议", "ignore": "忽略这条画像建议", "undo": "撤销这次画像确认"}
            service = ProfileProposalService(self.memory)
            return commands[action], lambda *args, **kwargs: service.act(*args, **kwargs, action=mapped)
        if action == "undo":
            return "撤销这次记忆确认", MemoryProposalUndoService(self.memory).undo
        service = MemoryProposalService(self.memory)
        if action == "ignore":
            return "不要保存这条记忆", service.reject
        return SAVE_CATEGORY if remember else SAVE_ONCE, lambda *args, **kwargs: service.accept(
            *args, **kwargs, remember_category=remember
        )

    def act(
        self, owner, subject, ident, *, action, revision, request_id, remember=False, change_type=None, choice=None
    ):
        if type(revision) is not int or revision < 1 or type(remember) is not bool:
            raise EvidenceError("记忆动作修订或确认参数无效")
        if action not in {"confirm", "ignore", "undo"} or (action != "confirm" and remember):
            raise EvidenceError("记忆动作无效")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            row = self.repo.get(owner, "proposal", ident, include_deleted=True)
            if row["subject_id"] != subject:
                raise ScopeError("所选记忆不属于当前人物")
            intent = [subject, ident, action, revision, remember, change_type, choice]
            binding = self.repo.mutation_request(
                owner,
                "memory2_web_binding",
                request_id,
                intent,
                lambda: {
                    "code": {"profile_doc": "profile", "memory_conflict": "conflict"}.get(
                        row.get("proposal_type"), "memory"
                    )
                },
            )
            if change_type is not None:
                if action != "undo" or change_type not in UNDO:
                    raise EvidenceError("记忆变更类型无效")
                factory, command = UNDO[change_type]
                handler = factory(self.memory).undo
            else:
                command, handler = self._handler(binding["code"], action, remember, choice)
            key = "memory2-web-" + fingerprint([owner, request_id])[:32]
            source = self.memory.receive(
                owner, subject, command, source_id=key, channel="web-action", role="user", at=get_clock().now()
            )
            return handler(owner, subject, ident, expected_revision=revision, message_id=source["id"], operation_id=key)

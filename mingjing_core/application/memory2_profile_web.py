"""Authenticated About Me edits preserve evidence and never edit original facts."""

from functools import partial

from mingjing_core.application.agent_tools_policy import CREDENTIAL, V4FactMemory
from mingjing_core.application.memory import SECRET
from mingjing_core.application.memory2_profile_reflection import checked_profile
from mingjing_core.application.memory2_proposals import approval_reference
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import fingerprint


class ProfileWebService:
    def __init__(self, repo):
        self.repo, self.memory = repo, V4FactMemory(repo)

    def view(self, owner, subject, ident):
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            row = checked_profile(self.memory, owner, subject, ident)
            return {key: row[key] for key in ("id", "revision", "section", "text", "confirmed_by_user")}

    def act(self, owner, subject, ident, *, revision, request_id, action, text=None):
        if type(revision) is not int or revision < 1 or action not in {"edit", "delete"}:
            raise EvidenceError("画像动作无效")
        if action == "edit" and (
            not isinstance(text, str)
            or not 1 <= len(text.strip()) <= 800
            or SECRET.search(text)
            or CREDENTIAL.search(text)
        ):
            raise EvidenceError("画像文字无效或包含不可存储内容")
        with self.repo.transaction(owner):
            self.repo.assert_scope(owner, subject)
            row = self.repo.get(owner, "profile_doc", ident, include_deleted=True)
            if row["subject_id"] != subject:
                raise ScopeError("画像条目不属于当前人物")
            key = "profile-web-" + fingerprint([owner, request_id])[:32]
            receipt = self.repo.mutation_request(
                owner,
                "memory2_profile_web",
                request_id,
                [subject, ident, revision, action, text],
                partial(self._apply, owner, subject, ident, revision, action, text, key),
            )
            current = self.repo.get(owner, "profile_doc", ident, include_deleted=True)
            if current["revision"] != receipt["revision"] or current["status"] != receipt["status"]:
                raise RevisionConflict("原画像操作结果已经变化")
            source = self.memory.get_source(owner, receipt["message_id"])
            verify_originals(self.memory, owner, subject, [approval_reference(source)])
            if action == "edit":
                checked_profile(self.memory, owner, subject, ident)
            return receipt

    def _apply(self, owner, subject, ident, revision, action, text, key):
        row = checked_profile(self.memory, owner, subject, ident)
        if row["revision"] != revision:
            raise RevisionConflict("画像已经变化，请刷新后重试")
        if action == "edit" and row["section"] == 7:
            raise EvidenceError("命理摘要需要原生档案依据，不能手工替换")
        command = "删除这条画像" if action == "delete" else "将这条画像改为：" + text
        source = self.memory.receive(owner, subject, command, source_id=key, channel="web-action", role="user")
        if action == "delete":
            result = self.repo.delete(owner, "profile_doc", ident, expected_revision=revision, operation_id=key)
        else:
            refs = [*row["source_refs"], approval_reference(source)]
            result = self.repo.update(
                owner,
                "profile_doc",
                ident,
                {
                    "text": text,
                    "edited_by_user": True,
                    "source_refs": refs,
                    "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
                },
                expected_revision=revision,
                operation_id=key,
            )
        self.repo.invalidate_derived(owner, [], [], recomputable=True, seed_entities=[("profile_doc", ident)])
        return {
            "id": ident,
            "kind": "profile_doc",
            "revision": result["revision"],
            "status": result["status"],
            "write_status": "deleted" if action == "delete" else "saved",
            "message_id": source["id"],
        }

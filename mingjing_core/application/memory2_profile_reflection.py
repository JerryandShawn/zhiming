"""Prepare background model input and commit its suggestions to the existing P3 proposal store."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from mingjing_core.application.agent_tools_policy import CREDENTIAL
from mingjing_core.application.memory import SECRET
from mingjing_core.application.memory2_fact_authority import authorized_fact, statement_instant
from mingjing_core.application.memory2_undo import verify_originals
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.memory.profile_doc import SECTION_TITLES, ProfileSuggestion, suggested_section
from mingjing_core.memory2.expiration import archive_deadline
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import get_clock

if TYPE_CHECKING:
    from mingjing_core.application.memory import MemoryService


def checked_profile_facts(memory: MemoryService, owner: str, subject: str, versions: dict[str, int]) -> list[dict]:
    if (
        not isinstance(versions, dict)
        or not versions
        or len(versions) > 100
        or any(not isinstance(ident, str) for ident in versions)
        or any(type(value) is not int or value < 1 for value in versions.values())
    ):
        raise EvidenceError("画像反思需要有限的已授权事实版本")
    current = {row["id"] for row in memory.facts(owner, subject)}
    rows = []
    settings = memory.repo.assert_scope(owner, subject)["settings"]
    now = get_clock().now()
    for ident, version in versions.items():
        row = authorized_fact(memory, owner, subject, ident, statuses=frozenset({"active"}))
        if row["revision"] != version:
            raise RevisionConflict("反思依据事实已经变化")
        if ident not in current or statement_instant(memory, owner, row) > now:
            raise EvidenceError("反思依据不是当前有效事实")
        zone = row.get("owner_timezone", settings.get("timezone", "Asia/Shanghai"))
        expiry = archive_deadline(dict(row, owner_timezone=zone))
        if expiry is not None and expiry <= now:
            raise EvidenceError("过期事件不能成为当前画像")
        rows.append(row)
    return rows


def checked_profile(memory: MemoryService, owner: str, subject: str, ident: str) -> dict:
    row = memory.repo.get(owner, "profile_doc", ident)
    if row["subject_id"] != subject:
        raise ScopeError("画像条目不属于当前人物")
    if row["status"] != "active" or not row.get("confirmed_by_user"):
        raise EvidenceError("画像条目尚未确认或已经失效")
    verify_originals(memory, owner, subject, row.get("source_refs", []))
    checked_profile_facts(memory, owner, subject, row.get("fact_versions", {}))
    return row


class ProfileReflectionService:
    def __init__(self, memory: MemoryService) -> None:
        self.memory, self.repo = memory, memory.repo

    def prepare(self, owner: str, subject: str, fact_ids: list[str], *, incognito: bool = False) -> dict:
        if incognito:
            raise EvidenceError("无痕内容不参与画像反思")
        if (
            not isinstance(fact_ids, list)
            or not 1 <= len(fact_ids) <= 100
            or any(not isinstance(ident, str) for ident in fact_ids)
        ):
            raise EvidenceError("画像反思需要有限事实范围")
        with self.repo.transaction(owner):
            versions = {ident: self.repo.get(owner, "fact", ident)["revision"] for ident in fact_ids}
            rows = checked_profile_facts(self.memory, owner, subject, versions)
            return {
                "sections": SECTION_TITLES,
                "fact_versions": versions,
                "facts": [
                    {
                        "id": row["id"],
                        "text": row["content"],
                        "suggested_section": suggested_section(row),
                        "source_ids": list(dict.fromkeys(ref["message_id"] for ref in row["source_refs"])),
                    }
                    for row in rows
                ],
                "unavailable_sections": {7: "等待有口径及可验证依据的命理档案接入"},
            }

    def propose(
        self, owner: str, subject: str, suggestions: list[dict], *, fact_versions: dict[str, int], operation_id: str
    ) -> dict[str, Any]:
        if not isinstance(suggestions, list) or not 1 <= len(suggestions) <= 20:
            raise EvidenceError("画像建议数量无效")
        try:
            parsed = [ProfileSuggestion.model_validate(value) for value in suggestions]
        except ValidationError:
            raise EvidenceError("画像建议结构无效") from None
        if any(row.section == 7 or SECRET.search(row.text) or CREDENTIAL.search(row.text) for row in parsed):
            raise EvidenceError("画像建议包含不可存储内容或缺少命理档案依据")
        with self.repo.transaction(owner):
            checked_profile_facts(self.memory, owner, subject, fact_versions)
            receipt = self.repo.mutation_request(
                owner,
                "memory2_profile_propose",
                operation_id,
                {"subject": subject, "suggestions": [row.model_dump() for row in parsed], "versions": fact_versions},
                partial(self._apply, owner, subject, parsed, fact_versions),
            )
            for ident in receipt["ids"]:
                row = self.repo.get(owner, "proposal", ident)
                if row["status"] != "pending":
                    raise EvidenceError("原画像建议已确认或失效")
                verify_originals(self.memory, owner, subject, row["source_refs"])
                checked_profile_facts(self.memory, owner, subject, row["fact_versions"])
            return receipt

    def consume_patch(
        self, owner: str, subject: str, ops: list[dict], *, fact_versions: dict[str, int], operation_id: str
    ) -> dict:
        """Consume profile_doc_patch add/update output; deletion requires its own user API."""
        if not isinstance(ops, list) or not 1 <= len(ops) <= 20:
            raise EvidenceError("画像整理操作数量无效")
        with self.repo.transaction(owner):
            rows = checked_profile_facts(self.memory, owner, subject, fact_versions)
            links = {row["id"]: {ref["message_id"] for ref in row["source_refs"]} for row in rows}
            suggestions = []
            for op in ops:
                if not isinstance(op, dict) or set(op) - {
                    "op",
                    "item_id",
                    "section",
                    "text",
                    "source_ids",
                    "confidence",
                }:
                    raise EvidenceError("画像整理操作结构无效")
                action, sources = op.get("op"), op.get("source_ids")
                if (
                    not isinstance(action, str)
                    or action not in {"add", "update"}
                    or not isinstance(sources, list)
                    or not sources
                    or any(not isinstance(ident, str) for ident in sources)
                ):
                    raise EvidenceError("画像整理仅接收有来源的新增或更新建议")
                if action == "add" and op.get("item_id") or action == "update" and not op.get("item_id"):
                    raise EvidenceError("画像整理目标无效")
                selected = [ident for ident, refs in links.items() if refs <= set(sources)]
                if not selected or set(sources) != set().union(*(links[ident] for ident in selected)):
                    raise EvidenceError("画像整理来源不在本次已授权事实范围")
                suggestions.append(
                    {
                        "section": op.get("section"),
                        "text": op.get("text"),
                        "fact_ids": selected,
                        "item_id": op.get("item_id"),
                        "confidence": op.get("confidence", 0.8),
                    }
                )
            return self.propose(owner, subject, suggestions, fact_versions=fact_versions, operation_id=operation_id)

    def _apply(self, owner: str, subject: str, suggestions: list[ProfileSuggestion], versions: dict) -> dict:
        ids = []
        for suggestion in suggestions:
            if not set(suggestion.fact_ids) <= versions.keys():
                raise EvidenceError("画像建议引用了未提供的事实")
            selected = {ident: versions[ident] for ident in dict.fromkeys(suggestion.fact_ids)}
            rows = checked_profile_facts(self.memory, owner, subject, selected)
            cases = {row.get("case_id") for row in rows}
            if len(cases) != 1:
                raise ScopeError("不同事项不能拼接为同一画像建议")
            target = checked_profile(self.memory, owner, subject, suggestion.item_id) if suggestion.item_id else None
            if target and (target["section"] != suggestion.section or target.get("case_id") not in cases):
                raise ScopeError("画像建议目标分节或事项不匹配")
            ident = self._record(owner, subject, suggestion, selected, rows, target)
            if ident not in ids:
                ids.append(ident)
        return {"write_status": "pending_confirmation", "ids": ids, "code": "memory2_profile_proposals"}

    def _record(
        self,
        owner: str,
        subject: str,
        suggestion: ProfileSuggestion,
        versions: dict,
        rows: list[dict],
        target: dict | None,
    ) -> str:
        ident = "profile_proposal_" + fingerprint([owner, subject, suggestion.model_dump(), versions, target])[0:32]
        refs = [ref for row in rows for ref in row["source_refs"]]
        if target:
            refs.extend(target["source_refs"])
        refs = [dict(items) for items in dict.fromkeys(tuple(sorted(ref.items())) for ref in refs)]
        old_versions = target["fact_versions"] if target else {}
        self.repo.put(
            owner,
            "proposal",
            ident,
            {
                "proposal_type": "profile_doc",
                "status": "pending",
                "inferred": True,
                "section": suggestion.section,
                "text": suggestion.text,
                "confidence": suggestion.confidence,
                "input_fact_versions": versions,
                "fact_ids": sorted(set(versions) | set(old_versions)),
                "fact_versions": dict(old_versions, **versions),
                "source_refs": refs,
                "source_ids": list(dict.fromkeys(ref["message_id"] for ref in refs)),
                "item_id": target["id"] if target else None,
                "target_revision": target["revision"] if target else 0,
            },
            subject=subject,
            case_id=rows[0].get("case_id"),
            expected_revision=0,
            operation_id=ident,
        )
        return ident

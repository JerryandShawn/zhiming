"""Native, owner-scoped, one-use consent; no consent is inferred from chat."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_projection import sources_active
from mingjing_core.application.charts_natal import natal_request
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import Clock, get_clock

KINDS = ("romantic", "friendship", "collaboration")


class ConsentRequired(EvidenceError):
    code = "CONSENT_REQUIRED"


@dataclass(frozen=True)
class ProfileScope:
    """Projection scope only; never represents a leased ToolContext."""

    owner: str
    subject: str
    case_ids: tuple[str, ...] = ()


def confirmed_snapshot(service: AgentToolsService, owner: str, subject: str) -> dict[str, Any]:
    service.repo.assert_scope(owner, subject)
    scope = ProfileScope(owner, subject)
    facts = [
        fact
        for fact in service.memory.facts(owner, subject, [])
        if (fact.get("field") == "gender" or str(fact.get("field", "")).startswith("birth."))
        and fact.get("consent") == "granted"
        and fact.get("assertion_status") == "user_asserted"
        and sources_active(service, fact, scope)
    ]
    versions = service.repo.versions(owner, subject, [])
    # Owner-wide writes include the consent itself. Only actual profile/source
    # dependencies bind this grant; unrelated writes cannot renew or invalidate it.
    versions = {"subject:" + subject: versions["subject:" + subject]}
    profile, conflicts = {}, set()
    for fact in facts:
        field = fact["field"]
        if field in profile and profile[field] != fact.get("value"):
            conflicts.add(field)
        profile[field] = fact.get("value")
        versions["fact:" + fact["id"]] = fact["revision"]
        for ref in fact.get("source_refs", []):
            versions["message:" + ref["message_id"]] = ref["version"]
    return {
        "owner_user_id": owner,
        "subject_id": subject,
        "revision": versions["subject:" + subject],
        "profile": profile,
        "profile_conflicts": sorted(conflicts),
        "versions": versions,
        "facts": facts,
    }


class SynastryConsentService:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.clock = repo, clock or get_clock()
        self.projection = AgentToolsService(repo, clock=self.clock)

    def _pair(self, owner: str, subject_a: str, subject_b: str, operation: str) -> list[dict[str, Any]]:
        if subject_a == subject_b:
            raise ScopeError("合盘需要同一账户下的另一位人物")
        snapshots = [confirmed_snapshot(self.projection, owner, subject) for subject in (subject_a, subject_b)]
        for snapshot in snapshots:
            natal_request(
                snapshot,
                owner=owner,
                subject=snapshot["subject_id"],
                operation_id=operation,
                as_of=self.clock.now().date().isoformat(),
            )
        return snapshots

    def _source(self, owner: str, subject: str, ident: str) -> dict[str, Any]:
        source = self.projection.memory.get_source(owner, ident)
        policy = source.get("policy", {})
        if (
            source.get("role") != "user"
            or source.get("channel") != "web"
            or source.get("private")
            or source.get("incognito")
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
        ):
            raise ConsentRequired("请在普通网页会话中确认合盘")
        cases = source.get("case_ids", [])
        if not isinstance(cases, list) or any(not isinstance(ident, str) for ident in cases):
            raise ScopeError("合盘请求事项范围无效")
        for case_id in cases:
            case = self.repo.get(owner, "case", case_id)
            if case["subject_id"] != subject or case["status"] != "open":
                raise ScopeError("合盘请求事项不属于当前人物")
        if not sources_active(self.projection, source, ProfileScope(owner, subject, tuple(cases)), "message"):
            raise ConsentRequired("合盘请求来源已失效")
        return source

    def request(
        self, owner: str, subject_a: str, subject_b: str, kind: str, source_id: str, request_id: str
    ) -> dict[str, Any]:
        if kind not in KINDS:
            raise EvidenceError("合盘用途无效")
        intent = [subject_a, subject_b, kind, source_id]
        ident = "synastry_consent_" + fingerprint([owner, request_id])[:32]
        with self.repo.transaction(owner):
            source = self._source(owner, subject_a, source_id)
            snapshots = self._pair(owner, subject_a, subject_b, ident)

            def effect() -> dict[str, Any]:
                versions = {key: value for snapshot in snapshots for key, value in snapshot["versions"].items()}
                versions["message:" + source_id] = source["revision"]
                facts = [fact for snapshot in snapshots for fact in snapshot["facts"]]
                row = self.repo.put(
                    owner,
                    "synastry_consent",
                    ident,
                    {
                        "subject_a": subject_a,
                        "subject_b": subject_b,
                        "comparison_kind": kind,
                        "state": "pending_confirmation",
                        "profile_revisions": [snapshot["revision"] for snapshot in snapshots],
                        "source_versions": versions,
                        "source_ids": [source_id],
                        "source_refs": [ref for fact in facts for ref in fact.get("source_refs", [])],
                        "used_fact_ids": [fact["id"] for fact in facts],
                        "uses_left": 0,
                    },
                    subject=subject_a,
                    expected_revision=0,
                    operation_id="synastry:request:" + request_id,
                )
                return {"id": row["id"], "revision": row["revision"], "status": "pending_confirmation"}

            receipt = self.repo.mutation_request(owner, "synastry_request", request_id, intent, effect)
            return self.card(owner, receipt["id"])

    def _current(self, owner: str, ident: str) -> dict[str, Any]:
        row = self.repo.get(owner, "synastry_consent", ident, include_deleted=True)
        if row["status"] != "active" or self.repo.is_revoked(owner, "synastry_consent", ident):
            raise ConsentRequired("原合盘确认已撤销，请重新确认")
        self._source(owner, row["subject_a"], row["source_ids"][0])
        if not self.repo.verify_versions(owner, row["source_versions"]):
            raise ConsentRequired("出生资料或来源已改变，请重新确认合盘")
        self._pair(owner, row["subject_a"], row["subject_b"], ident)
        return row

    def card(self, owner: str, ident: str) -> dict[str, Any]:
        with self.repo.transaction(owner):
            row = self._current(owner, ident)
            label = self.repo.assert_scope(owner, row["subject_b"])["label"]
            expired = (
                row.get("expires_at") is not None and datetime.fromisoformat(row["expires_at"]) <= self.clock.now()
            )
            return {
                "id": ident,
                "revision": row["revision"],
                "kind": row["comparison_kind"],
                "state": "expired" if expired else row["state"],
                "subject_a": row["subject_a"],
                "subject_b": row["subject_b"],
                "message": f"合盘会用到〈{label}〉的出生资料。请确认对方知道并同意这次比较。只做这一次，不保存结果、不转发。",
                "expires_at": row.get("expires_at"),
                "uses_left": 0 if expired else row["uses_left"],
            }

    def confirm(
        self, owner: str, ident: str, *, confirmed: bool, expected_revision: int, request_id: str
    ) -> dict[str, Any]:
        if confirmed is not True or type(expected_revision) is not int:
            raise ConsentRequired("需要在网页上明确点击确认本次合盘")
        with self.repo.transaction(owner):

            def effect() -> dict[str, Any]:
                row = self._current(owner, ident)
                if row["revision"] != expected_revision:
                    raise RevisionConflict("确认卡片已改变，请刷新后重试")
                if row["state"] != "pending_confirmation":
                    raise ConsentRequired("本次确认已使用，请创建新的确认卡片")
                now = self.clock.now()
                updated = self.repo.update(
                    owner,
                    "synastry_consent",
                    ident,
                    {
                        "state": "granted",
                        "uses_left": 1,
                        "granted_at": now.isoformat(),
                        "expires_at": (now + timedelta(hours=24)).isoformat(),
                        "grant_operation_id": request_id,
                    },
                    expected_revision=expected_revision,
                    operation_id="synastry:confirm:" + request_id,
                )
                return {"id": ident, "revision": updated["revision"], "status": "granted"}

            self.repo.mutation_request(
                owner, "synastry_confirm", request_id, [ident, expected_revision, confirmed], effect
            )
            return self.card(owner, ident)

    def cards_for_conversation(self, owner: str, conversation_id: str) -> list[dict[str, Any]]:
        """Discover native cards, never a model-supplied confirmation payload."""
        cards = []
        with self.repo.transaction(owner):
            for row in self.repo.list(owner, "synastry_consent", subject="self", order="desc", limit=100):
                if row.get("state") not in {"pending_confirmation", "granted"}:
                    continue
                try:
                    source = self._source(owner, row["subject_a"], row["source_ids"][0])
                    if source.get("conversation_id") != conversation_id:
                        continue
                    card = self.card(owner, row["id"])
                except CoreError:
                    # Withdrawn/stale cards remain private audit records, not actionable UI.
                    continue
                if card["state"] != "expired":
                    cards.append(card)
                if len(cards) == 20:
                    break
        return cards

    def find_granted(self, owner: str, subject_a: str, subject_b: str, kind: str, conversation: str) -> str | None:
        with self.repo.transaction(owner):
            for row in self.repo.list(owner, "synastry_consent", subject=subject_a, order="desc", limit=100):
                if (row.get("subject_b"), row.get("comparison_kind"), row.get("state")) != (subject_b, kind, "granted"):
                    continue
                try:
                    current = self._current(owner, row["id"])
                    source = self._source(owner, subject_a, current["source_ids"][0])
                except CoreError:
                    continue
                if (
                    source.get("conversation_id") == conversation
                    and current["uses_left"] == 1
                    and (datetime.fromisoformat(current["expires_at"]) > self.clock.now())
                ):
                    return current["id"]
        return None

    def consume(self, owner: str, ident: str, *, subject_a: str, subject_b: str, kind: str, operation_id: str) -> dict:
        """Internal boundary only; callers must fence their native leased step."""
        if not isinstance(operation_id, str) or not 1 <= len(operation_id) <= 180:
            raise EvidenceError("合盘需要稳定执行标识")
        with self.repo.transaction(owner):
            row = self._current(owner, ident)
            if (row["subject_a"], row["subject_b"], row["comparison_kind"]) != (subject_a, subject_b, kind):
                raise ConsentRequired("本次确认不适用于这组人物或用途")
            if row["state"] != "granted" or type(row["uses_left"]) is not int or row["uses_left"] != 1:
                raise ConsentRequired("请先在网页确认本次合盘")
            if datetime.fromisoformat(row["expires_at"]) <= self.clock.now():
                raise ConsentRequired("本次确认已超过24小时，请重新确认")
            self.repo.update(
                owner,
                "synastry_consent",
                ident,
                {"state": "consumed", "uses_left": 0, "consumed_by": operation_id},
                expected_revision=row["revision"],
                operation_id="synastry:consume:" + operation_id,
            )
            snapshots = self._pair(owner, subject_a, subject_b, operation_id)
            return {"consent": "user_confirmed", "snapshots": snapshots, "consent_id": ident}

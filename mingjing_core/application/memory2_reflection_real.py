"""Real-model idle reflection over new thread messages (plan 50 §3/§6, user ruling (b) of 2026-11-08).

Explicit, non-sensitive user statements are written as revocable facts; sensitive, third-party, inferred and
event items become pending proposals. Every derived row carries its source message ids, so deleting an
original removes it through the existing privacy closure and revocation ledger.
"""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_tools_memory import source_ref
from mingjing_core.application.agent_tools_policy import (
    SENSITIVITIES,
    V4FactMemory,
    sensitivity,
    sensitivity_categories,
)
from mingjing_core.application.memory2_background_reflection import IdleMemoryReflection
from mingjing_core.application.memory2_reflection_input import (
    TASK,
    advance_cursor,
    build_input,
    memory_enabled,
    owner_day,
    require_thread_message,
    reserve_budget,
)
from mingjing_core.application.memory2_reflection_model import ReflectionModel
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.memory.policy import hypothetical
from mingjing_core.repositories.postgres import fingerprint

AUTO_KINDS = frozenset({"preference", "constraint", "background", "goal"})
ORIGIN = "memory2_reflection"


class RealMemoryReflection:
    def __init__(self, repo: Any, clock: Any, *, model: ReflectionModel, daily_limit: int | None = None) -> None:
        self.repo, self.clock, self.model, self.daily_limit = repo, clock, model, daily_limit
        self.memory = V4FactMemory(repo)
        # Reuse the scripted path's eligibility: life thread, not incognito, idle >= 10 min, no run in flight.
        self.gate = IdleMemoryReflection(repo, clock)

    def thread(self, owner: str, ident: str, subject: str) -> str:
        key = self.repo.schema + ":memory2-reflection:" + owner + ":" + ident
        with self.repo.pool.connection() as connection:
            locked = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", (key,)).fetchone()
            if not locked["ok"]:
                return "busy"
            try:
                return self._run(owner, ident, subject)
            finally:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    def _prepare(self, owner: str, ident: str, subject: str) -> tuple[str, dict, dict | None] | str:
        with self.repo.transaction(owner):
            try:
                thread = self.gate._ready(owner, ident, subject)
            except CoreError:
                return "ineligible"
            if not memory_enabled(self.repo, owner, subject):
                return "memory_off"
            payload = build_input(self.repo, self.memory, owner, subject, ident)
            if payload is None:
                return "unchanged"
            job = (
                "memory2-reflect-real-"
                + fingerprint([owner, ident, payload["through_ms"], thread["last_activity_at"]])[:32]
            )
            if not payload["messages"]:
                advance_cursor(self.repo, owner, subject, ident, payload["through_ms"], job)
                return "unchanged"
            try:
                self.repo.get(owner, "runtime_step", job, include_deleted=True)
            except ScopeError:
                pass
            else:
                # Same input already attempted (failed or superseded): never re-spend budget on it.
                return "unchanged"
            day = owner_day(self.repo, owner, subject, self.clock.now())
            if not reserve_budget(self.repo, owner, subject, day, job, self.daily_limit):
                return "budget_exhausted"
            record = self.repo.put(
                owner,
                "runtime_step",
                job,
                {
                    "task": TASK,
                    "state": "running",
                    "thread_id": ident,
                    "activity": thread["last_activity_at"],
                    "day": day,
                    "through_ms": payload["through_ms"],
                    "source_ids": [row["id"] for row in payload["messages"]],
                },
                subject=subject,
                expected_revision=0,
                operation_id=job,
            )
            return job, record, payload

    def _run(self, owner: str, ident: str, subject: str) -> str:
        prepared = self._prepare(owner, ident, subject)
        if isinstance(prepared, str):
            return prepared
        job, record, payload = prepared
        try:
            items = self.model.extract({"messages": payload["messages"], "profile": payload["profile"]})
            with self.repo.transaction(owner):
                current = ThreadService(self.repo, clock=self.clock).get(owner, ident, subject=subject)
                if current["last_activity_at"] == record["activity"]:
                    current = self.gate._ready(owner, ident, subject)
                if current["last_activity_at"] != record["activity"]:
                    # New text arrived meanwhile: discard this result; the next idle window re-reads.
                    self._finish(owner, record, {"state": "superseded"})
                    return "superseded"
                counts, fact_ids, proposal_ids = self._apply(owner, subject, ident, job, items)
                advance_cursor(self.repo, owner, subject, ident, payload["through_ms"], job)
                self._finish(
                    owner,
                    record,
                    {"state": "completed", "counts": counts, "fact_ids": fact_ids, "proposal_ids": proposal_ids},
                )
            return "completed"
        except Exception:
            with self.repo.transaction(owner):
                current = self.repo.get(owner, "runtime_step", record["id"], include_deleted=True)
                if current["status"] != "deleted":
                    self._finish(owner, current, {"state": "failed", "code": "MEMORY_REFLECTION_FAILED"})
            return "failed"

    def _finish(self, owner: str, record: dict, changes: dict) -> None:
        current = self.repo.get(owner, "runtime_step", record["id"], include_deleted=True)
        if current["status"] == "deleted":
            return
        self.repo.update(owner, "runtime_step", current["id"], changes, expected_revision=current["revision"])

    def _apply(
        self, owner: str, subject: str, ident: str, job: str, items: list[dict]
    ) -> tuple[dict[str, int], list[str], list[str]]:
        counts = {"saved": 0, "pending": 0, "skipped": 0}
        fact_ids: list[str] = []
        proposal_ids: list[str] = []
        for index, item in enumerate(items):
            operation = job + ":item:" + str(index)
            try:
                outcome, row_id = self._item(owner, subject, ident, item, operation)
            except CoreError:
                outcome, row_id = "skipped", None
            counts[outcome] += 1
            if outcome == "saved" and row_id not in fact_ids:
                fact_ids.append(row_id)
            elif outcome == "pending" and row_id not in proposal_ids:
                proposal_ids.append(row_id)
        return counts, fact_ids, proposal_ids

    def _item(self, owner: str, subject: str, ident: str, item: dict, operation: str) -> tuple[str, str | None]:
        message = require_thread_message(self.repo, owner, subject, ident, item["message_id"])
        content, quote = message["content"], item["quote"]
        if content.count(quote) != 1:
            raise EvidenceError("反思原话必须在原消息中逐字且唯一")
        start = content.index(quote)
        end = start + len(quote)
        level = sensitivity(quote, content, start, end)
        if level in {"secret", "profile"}:
            return "skipped", None
        if item["kind"] != "concern" and hypothetical(content, start, end):
            return "skipped", None
        auto = item["explicit"] and item["kind"] in AUTO_KINDS and level == "normal" and subject == "self"
        if auto:
            saved = self._auto_save(owner, subject, message, start, end, item, operation)
            if saved is not None:
                return "saved", saved
        return "pending", self._propose(owner, subject, message, start, end, item, level, operation)

    def _auto_save(
        self, owner: str, subject: str, message: dict, start: int, end: int, item: dict, operation: str
    ) -> str | None:
        # User ruling (b) uses the same v4 save policy as an in-turn memory_write: no extra authority is
        # minted here, so opt-outs, revoked ranges, secrets and the low-sensitivity switch all still apply.
        row = self.memory.save_fact(
            owner, subject, message["id"], item["quote"], item["kind"], operation_id=operation + ":fact"
        )
        if row.get("write_status") != "saved":
            return None
        if row.get("origin") is None:
            row = self.repo.update(
                owner,
                "fact",
                row["id"],
                {"origin": ORIGIN, "summary": item["summary"], "auto_written": True},
                expected_revision=row["revision"],
                operation_id=operation + ":metadata",
            )
        return row["id"]

    def _propose(
        self, owner: str, subject: str, message: dict, start: int, end: int, item: dict, level: str, operation: str
    ) -> str:
        ident = "proposal_" + fingerprint([owner, ORIGIN, message["id"], start, end, item["kind"]])[:32]
        try:
            existing = self.repo.get(owner, "proposal", ident, include_deleted=True)
        except ScopeError:
            existing = None
        if existing is not None:
            return ident
        self.repo.put(
            owner,
            "proposal",
            ident,
            {
                "status": "pending",
                "origin": ORIGIN,
                "kind": item["kind"],
                "sensitivity": level,
                "categories": list(sensitivity_categories(item["quote"], message["content"], start, end)),
                "summary": item["summary"],
                # Events carry no pre-resolved dates: acceptance resolves and verifies the absolute date itself.
                **(
                    {}
                    if item["kind"] == "event"
                    else {"fact_metadata": {"summary": item["summary"], "requested_kind": item["kind"]}}
                ),
                "source_ids": [message["id"]],
                "source_refs": [source_ref(message, start, end)],
                "inferred": not item["explicit"],
                "needs_confirmation_reason": "sensitive" if level in SENSITIVITIES else "inferred_or_event",
            },
            subject=subject,
            expected_revision=0,
            operation_id=operation + ":proposal",
        )
        return ident

"""Bounded source snapshots reuse the real memory writer's privacy projections."""

from __future__ import annotations

import copy
from typing import Any

from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.memory2_read_authority import fact_consent_versions
from mingjing_core.domain.contracts import ScopeError
from mingjing_core.domain.time_ranges import TimeRangeParser
from mingjing_core.memory.projections import redact_ranges
from mingjing_core.repositories.dependencies import entity_dependency

from .context_entities import read_entities
from .context_time_retrieval import retrieve
from .context_types import BudgetPolicy, ContextInputError, SourceSnapshot


class BoundedSources:
    def __init__(
        self,
        memory: MemoryService,
        policy: BudgetPolicy,
        *,
        run_context: dict | None = None,
        time_parser: TimeRangeParser | None = None,
    ) -> None:
        from mingjing_core.application.time_range_parser import ModuleTimeRangeParser

        self.memory, self.repo, self.policy = memory, memory.repo, policy
        self.cache: dict[str, dict[str, Any]] = {}
        self.spans: dict[str, list[dict[str, Any]]] = {}
        self.deleted: set[str] = set()
        self.boundary: tuple[int, str, str] | None = None
        self.history_counts: dict[str, int] = {}
        self.run_context = run_context
        self.time_parser = time_parser or ModuleTimeRangeParser()

    @staticmethod
    def _key(source: dict[str, Any]) -> tuple[int, str, str]:
        if type(source.get("at_ms")) is not int:
            raise ContextInputError("context_source_time_invalid")
        return source["at_ms"], source["created_at"], source["id"]

    def _set_boundary(self, owner: str, subject: str, source: dict[str, Any]) -> None:
        if self.run_context is not None:
            from mingjing_core.application.agent_source_boundary import authorize_boundary

            authorize_boundary(self.repo, owner, subject, source, self.run_context)
            self.boundary = self._key(source)
            self._reject_ambiguous_boundary(owner, subject, source)
            return
        with self.repo.transaction(owner) as connection:
            query = sql.SQL("""SELECT id FROM {} WHERE owner=%s AND subject=%s AND kind='message'
                AND status='active' AND data->>'thread_id'=%s AND data->>'role'='user'
                ORDER BY (data->>'at_ms')::bigint DESC,created_at DESC,id DESC LIMIT 1""").format(
                self.repo.table("core_entities")
            )
            latest = connection.execute(query, (owner, subject, "life:" + subject)).fetchone()
        if latest is None or latest["id"] != source["id"]:
            raise ContextInputError("context_current_not_latest")
        self.boundary = self._key(source)
        self._reject_ambiguous_boundary(owner, subject, source)

    def _reject_ambiguous_boundary(self, owner: str, subject: str, source: dict[str, Any]) -> None:
        with self.repo.transaction(owner) as connection:
            query = sql.SQL("""SELECT 1 FROM {} WHERE owner=%s AND subject=%s AND kind='message'
                AND status='active' AND data->>'thread_id'=%s AND (data->>'at_ms')::bigint=%s
                AND created_at=%s::timestamptz AND id!=%s LIMIT 1""").format(self.repo.table("core_entities"))
            ambiguous = connection.execute(query, (owner, subject, "life:" + subject, *self.boundary)).fetchone()
        if ambiguous:
            raise ContextInputError("context_source_order_ambiguous")

    def _history(self, owner: str, subject: str, cases: tuple[str, ...]) -> list[dict[str, Any]]:
        with self.repo.transaction(owner) as connection:
            query = sql.SQL("""WITH timeline AS (SELECT *,
                row_number() OVER (ORDER BY (data->>'at_ms')::bigint,created_at,id) AS context_ordinal,
                count(*) OVER () AS context_total,
                sum((data->>'role'='user')::int) OVER () AS user_rounds
                FROM {} WHERE owner=%s AND subject=%s AND kind='message'
                AND status='active' AND data->>'thread_id'=%s
                AND (coalesce(data->'case_ids','[]')='[]'::jsonb OR data->'case_ids' ?| %s)
                AND ((data->>'at_ms')::bigint,created_at,id)<= (%s,%s::timestamptz,%s))
                SELECT * FROM timeline
                ORDER BY (data->>'at_ms')::bigint DESC,created_at DESC,id DESC LIMIT %s""").format(
                self.repo.table("core_entities")
            )
            rows = connection.execute(
                query,
                (
                    owner,
                    subject,
                    "life:" + subject,
                    list(cases),
                    *self.boundary,
                    self.policy.history_limit,
                ),
            ).fetchall()
        decoded = [dict(self.repo._decode(row), _context_ordinal=row["context_ordinal"]) for row in reversed(rows)]
        self.history_counts = {
            "thread_user_rounds": rows[0]["user_rounds"] if rows else 0,
            "history_truncated": int(bool(rows and rows[0]["context_total"] > len(rows))),
        }
        self.cache.update({row["id"]: row for row in decoded})
        return decoded

    def _catalog_count(self, owner: str, subject: str, cases: tuple[str, ...]) -> tuple[int, int]:
        with self.repo.transaction(owner) as connection:
            fact_query = sql.SQL("""SELECT count(*) AS count FROM (
                SELECT 1 FROM {} WHERE owner=%s AND subject=%s AND kind='fact'
                AND status!='deleted' AND (case_id IS NULL OR case_id=ANY(%s)) LIMIT %s) bounded""").format(
                self.repo.table("core_entities")
            )
            fact_count = connection.execute(
                fact_query, (owner, subject, list(cases), self.policy.fact_limit + 1)
            ).fetchone()["count"]
            revoke_query = sql.SQL("""SELECT count(*) AS count FROM (
                SELECT 1 FROM {} WHERE owner=%s LIMIT %s) bounded""").format(self.repo.table("core_revocations"))
            revoke_count = connection.execute(revoke_query, (owner, self.policy.revocation_limit + 1)).fetchone()[
                "count"
            ]
        if fact_count > self.policy.fact_limit or revoke_count > self.policy.revocation_limit:
            raise ContextInputError("context_source_catalog_overflow")
        return fact_count, revoke_count

    def _source(self, owner: str, ident: str) -> dict[str, Any]:
        if ident not in self.cache:
            if len(self.cache) >= self.policy.source_ref_limit + self.policy.history_limit + self.policy.search_limit:
                raise ContextInputError("context_source_catalog_overflow")
            self.cache[ident] = self.memory.get_source(owner, ident)
        return self.cache[ident]

    def _reference_valid(self, owner: str, subject: str, ref: dict[str, Any]) -> bool:
        try:
            ident, start, end, quote = (ref[key] for key in ("message_id", "start", "end", "quote"))
            source = self._source(owner, ident)
        except (KeyError, ScopeError):
            return False
        if type(start) is not int or type(end) is not int or not isinstance(quote, str):
            return False
        if source["subject_id"] != subject or source["status"] != "active" or source.get("role") != "user":
            return False
        if ident in self.deleted or source["revision"] != ref.get("version"):
            return False
        if self.boundary is not None and self._key(source) > self.boundary:
            return False
        text = source.get("content", "")
        if not 0 <= start < end <= len(text) or text[start:end] != quote:
            return False
        for span in self.spans.get(ident, []):
            left, right = span.get("start"), span.get("end")
            if type(left) is not int or type(right) is not int or not 0 <= left < right <= len(text):
                return False
            if max(start, left) < min(end, right):
                return False
        return True

    def _facts(self, owner: str, subject: str, cases: tuple[str, ...]) -> list[dict[str, Any]]:
        candidates = self.memory.facts(owner, subject, list(cases))
        if sum(len(fact.get("source_refs", [])) for fact in candidates) > self.policy.source_ref_limit:
            raise ContextInputError("context_source_catalog_overflow")
        return [
            fact
            for fact in candidates
            if fact.get("source_refs")
            and all(self._reference_valid(owner, subject, ref) for ref in fact["source_refs"])
            and any(ref.get("quote") == fact.get("content") for ref in fact["source_refs"])
        ]

    def _project(
        self,
        owner: str,
        subject: str,
        row: dict[str, Any],
        facts: list[dict[str, Any]],
        cases: tuple[str, ...],
    ) -> dict[str, Any] | None:
        original = self._source(owner, row["id"])
        if original["subject_id"] != subject or original["status"] != "active" or original["id"] in self.deleted:
            return None
        if original.get("role") not in {"user", "assistant"}:
            return None
        if original.get("thread_id") != "life:" + subject:
            return None
        if self.boundary is not None and self._key(original) > self.boundary:
            return None
        linked = set(original.get("case_ids", []))
        if linked and not linked.intersection(cases):
            return None
        text = redact_ranges(original.get("content", ""), self.spans.get(original["id"], []))
        if linked - set(cases):
            quotes = [
                fact["content"]
                for fact in facts
                if fact.get("content") in text
                and any(ref.get("message_id") == original["id"] for ref in fact.get("source_refs", []))
            ]
            text = "\n".join(dict.fromkeys(quotes))
        return dict(original, content=text) if text else None

    def _revocations(self, owner: str) -> None:
        for row in self.repo.revocations(owner):
            if row["kind"] == "message":
                self.deleted.add(row["entity_id"])
            elif row["kind"] == "source_span":
                span = row["metadata"]
                self.spans.setdefault(span.get("message_id"), []).append(span)

    def _current(
        self,
        owner: str,
        subject: str,
        ident: str,
        facts: list[dict[str, Any]],
        cases: tuple[str, ...],
    ) -> dict[str, Any]:
        original = self._source(owner, ident)
        policy = original.get("policy", {})
        if original.get("role") != "user" or policy.get("origin") != "current_user" or not policy.get("run_context"):
            raise ContextInputError("context_current_source_invalid")
        projected = self._project(owner, subject, original, facts, cases)
        if projected is None:
            raise ContextInputError("context_current_source_invalid")
        return projected

    def _retrieved(
        self,
        owner: str,
        subject: str,
        query: str,
        facts: list[dict[str, Any]],
        cases: tuple[str, ...],
        current: dict[str, Any],
        zone: str,
    ) -> tuple[list[dict[str, Any]], int, str | None]:
        return retrieve(self, owner, subject, query, facts, cases, current, zone)

    def read(
        self,
        owner: str,
        subject: str,
        source_message_id: str,
        *,
        thread_id: str,
        case_ids: tuple[str, ...] = (),
        query: str | None = None,
    ) -> SourceSnapshot:
        if thread_id != "life:" + subject or len(case_ids) > 8:
            raise ContextInputError("context_thread_unsupported")
        with self.repo.transaction(owner):
            scope = self.repo.assert_scope(owner, subject)
            for ident in case_ids:
                if self.repo.get(owner, "case", ident)["subject_id"] != subject:
                    raise ScopeError("事项不属于当前人物。")
            fact_count, revocation_count = self._catalog_count(owner, subject, case_ids)
            self._revocations(owner)
            self._set_boundary(owner, subject, self._source(owner, source_message_id))
            facts = self._facts(owner, subject, case_ids)
            current = self._current(owner, subject, source_message_id, facts, case_ids)
            rows = self._history(owner, subject, case_ids)
            history = [self._project(owner, subject, row, facts, case_ids) for row in rows]
            history = [row for row in history if row is not None and row["id"] != source_message_id]
            retrieved, search_count, time_filter = self._retrieved(
                owner,
                subject,
                query or current["content"],
                facts,
                case_ids,
                current,
                scope["settings"].get("timezone", "Asia/Shanghai"),
            )
            retrieved = [row for row in retrieved if row["id"] != source_message_id]
            entities = read_entities(self, owner, subject, case_ids, facts)
            versions = {"message:" + row["id"]: row["revision"] for row in self.cache.values()}
            versions.update({"fact:" + fact["id"]: fact["revision"] for fact in facts})
            consent_versions = fact_consent_versions(self.memory, owner, subject, facts)
            if len(consent_versions) > self.policy.source_ref_limit:
                raise ContextInputError("context_source_catalog_overflow")
            versions.update(consent_versions)
            versions.update(
                {entity_dependency(kind, row["id"]): row["revision"] for kind, rows in entities.items() for row in rows}
            )
            counts = {
                "fact_catalog": fact_count,
                "revocations": revocation_count,
                "history_candidates": len(rows),
                "search_candidates": search_count,
                "source_cache_entries": len(self.cache),
                "extra_candidates": sum(len(rows) for rows in entities.values()),
                **self.history_counts,
            }
            return copy.deepcopy(
                SourceSnapshot(
                    owner,
                    subject,
                    scope["revision"],
                    scope["settings"],
                    tuple(facts),
                    tuple(history),
                    tuple(retrieved),
                    current,
                    versions,
                    counts,
                    entities,
                    time_filter,
                )
            )

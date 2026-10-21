"""Bounded UI projection includes interrupted replies without making them model evidence."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.threads import project_sources


def thread_history(repo: Any, owner: str, ident: str, *, subject: str = "self", limit: int = 80) -> list[dict]:
    ThreadService(repo).get(owner, ident, subject=subject)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise EvidenceError("线程历史数量无效")
    memory = MemoryService(repo)
    with repo.transaction(owner) as connection:
        raw = connection.execute(
            sql.SQL(
                "SELECT id FROM {} WHERE owner=%s AND subject=%s AND kind='message' "
                "AND status IN ('active','interrupted') AND data->>'thread_id'=%s "
                "ORDER BY (data->>'at_ms')::bigint DESC,created_at DESC,id DESC LIMIT %s"
            ).format(repo.table("core_entities")),
            (owner, subject, ident, limit),
        ).fetchall()
        rows = [memory.get_source(owner, row["id"], for_context=True) for row in reversed(raw)]
        selected = set()
        for case_id in {case_id for row in rows for case_id in row.get("case_ids", [])}:
            try:
                case = repo.get(owner, "case", case_id)
                if (
                    case["subject_id"] == subject
                    and case["status"] != "deleted"
                    and not repo.is_revoked(owner, "case", case_id)
                ):
                    selected.add(case_id)
            except (ScopeError, EvidenceError):
                continue
        projected = project_sources(
            memory, owner, rows, [], selected, private_thread=ident if ident.startswith("incognito:") else None
        )
    fields = ("id", "role", "content", "at", "thread_id", "run_id", "status", "incognito", "case_ids")
    return [{key: row[key] for key in fields if key in row} for row in projected]

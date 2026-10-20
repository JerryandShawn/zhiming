"""Resolve each ingress original independently; never manufacture a joined user quote."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository


def ingress_sources(
    repo: PostgresRepository, owner: str, subject: str, thread: str, identifiers: list[str]
) -> list[dict[str, Any]]:
    if (
        not isinstance(identifiers, list)
        or not 1 <= len(identifiers) <= 64
        or any(not isinstance(ident, str) for ident in identifiers)
        or len(set(identifiers)) != len(identifiers)
    ):
        raise EvidenceError("入站原话列表需要一至64条独立来源")
    ThreadService(repo).get(owner, thread, subject=subject)
    memory, rows = MemoryService(repo), []
    for ident in identifiers:
        row = memory.get_source(owner, ident)
        projected = memory.get_source(owner, ident, for_context=True)
        policy = row.get("policy", {})
        if row["subject_id"] != subject or row.get("thread_id") != thread:
            raise ScopeError("入站原话不属于当前人物与线程")
        if (
            row["status"] != "active"
            or row.get("role") != "user"
            or not row.get("content", "").strip()
            or policy.get("origin") != "current_user"
            or policy.get("run_context") is not True
            or row.get("content") != projected.get("content")
            or repo.is_revoked(owner, "message", ident)
        ):
            raise EvidenceError("入站原话已撤销或不具备当前用户授权")
        rows.append(row)
    return sorted(rows, key=lambda row: (row["at_ms"], row["created_at"], row["id"]))


def source_segments(sources: list[dict[str, Any]]) -> list[dict[str, str | int]]:
    return [dict(message_id=row["id"], version=row["revision"], start=0, end=len(row["content"])) for row in sources]

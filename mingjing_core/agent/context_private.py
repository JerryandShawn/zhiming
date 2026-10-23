"""Private context uses only this owner/thread's temporary, projected messages."""

from typing import Any

from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.memory.private import is_private
from mingjing_core.repositories.dependencies import entity_dependency

from .context_types import BudgetPolicy, SourceSnapshot


def private_sources(
    memory: Any,
    owner: str,
    subject: str,
    ident: str,
    current_id: str,
    policy: BudgetPolicy,
    *,
    run_context: dict | None = None,
) -> SourceSnapshot:
    repo = memory.repo
    threads = ThreadService(repo)
    with repo.transaction(owner):
        scope = repo.assert_scope(owner, subject)
        threads.get(owner, ident, subject=subject)
        current = memory.get_source(owner, current_id, for_context=True)
        if run_context is not None:
            from mingjing_core.application.agent_source_boundary import authorize_boundary

            authorize_boundary(repo, owner, subject, current, run_context)
        rows = threads.history(
            owner, ident, subject=subject, limit=policy.history_limit, through=current_id if run_context else None
        )
        users = [row for row in rows if row.get("role") == "user"]
        if (
            not users
            or run_context is None
            and users[-1]["id"] != current_id
            or current.get("thread_id") != ident
            or not is_private(current)
            or current.get("role") != "user"
            or current.get("status") != "active"
            or current.get("policy", {}).get("origin") != "current_user"
            or current.get("policy", {}).get("run_context") is not True
            or repo.is_revoked(owner, "message", current_id)
        ):
            raise EvidenceError("无痕上下文需要当前线程最新有效用户原话")
        projected = next((row for row in rows if row["id"] == current_id), None)
        if projected is None or projected.get("content") != current.get("content"):
            raise EvidenceError("无痕原话已部分撤销，不能复用旧运行")
        before = rows[: rows.index(projected)]
        versions = {entity_dependency("message", row["id"]): row["revision"] for row in [*before, current]}
        return SourceSnapshot(
            owner,
            subject,
            scope["revision"],
            scope["settings"],
            (),
            tuple(before),
            (),
            current,
            versions,
            {"history_candidates": len(rows), "thread_user_rounds": len(users), "private": 1},
            {},
        )

"""Body-free acknowledgements and read-only routing from persisted identity."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.thread_queue import owner_runtime
from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError


def submission_target(
    repo: Any, owner: str, subject: str, request_id: str
) -> tuple[str, Any]:
    """The caller can retain the owner transaction through submit to fence settings."""
    with repo.transaction(owner) as connection:
        existing = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s").format(
                repo.table("core_runs")
            ),
            (owner, request_id),
        ).fetchone()
        if existing is not None:
            return existing["runtime"], existing
        row = connection.execute(
            sql.SQL("SELECT settings FROM {} WHERE id=%s").format(
                repo.table("core_owners")
            ),
            (owner,),
        ).fetchone()
        if row is None:
            # Inspecting a default-v3 request must not create an owner on a 406.
            return "v3", None
        scope = repo.assert_scope(owner, subject)
        return owner_runtime(scope["settings"]), None


def run_acceptance(repo: Any, owner: str, run_id: str) -> dict[str, str]:
    with repo.transaction(owner):
        run = repo.fetch_run(owner, run_id)
        repo.assert_scope(owner, run["subject"])
        request, thread = run["request"], run.get("thread_id")
        primary = request.get("source_message_id")
        identifiers = request.get("source_message_ids", [primary])
        if not isinstance(thread, str) or not isinstance(primary, str):
            raise EvidenceError("原运行缺少已核对的消息与线程身份")
        sources = ingress_sources(repo, owner, run["subject"], thread, identifiers)
        if (
            sources[-1]["id"] != primary
            or sources[-1]["content"] != request.get("message")
            or request.get("source_segments") is not None
            and request["source_segments"] != source_segments(sources)
        ):
            raise EvidenceError("原运行的消息来源已改变，不能生成接收回执")
        result = {
            "run_id": run["id"],
            "message_id": primary,
            "thread_id": thread,
            "status": run["status"],
            "runtime": run["runtime"],
            "run_url": "/api/runs/" + run["id"],
        }
        if run["runtime"] == "v4":
            result["events_url"] = result["run_url"] + "/events"
        return result

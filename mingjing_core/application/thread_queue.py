"""Pin routing before transaction commit; original operation IDs retain their runtime."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.thread_sources import ingress_sources, source_segments
from mingjing_core.domain.contracts import EvidenceError, ScopeError

RESERVED_OPTIONS = frozenset(
    {
        "runtime",
        "incognito",
        "thread_id",
        "lane",
        "source_message_id",
        "source_message_ids",
        "message",
        "source_segments",
        "owner",
        "subject",
        "request_id",
        "conversation_id",
    }
)


def owner_runtime(settings: dict[str, Any]) -> str:
    runtime = settings.get("runtime", "v3")
    if not isinstance(runtime, str) or runtime not in {"v3", "v4"}:
        raise EvidenceError("持久运行时设置无效")
    return runtime


def active_thread_run(repo: Any, connection: Any, owner: str, subject: str, thread: str) -> dict[str, Any] | None:
    return connection.execute(
        sql.SQL(
            "SELECT * FROM {} WHERE owner=%s AND subject=%s AND status='running' AND lease_until>now() "
            "AND coalesce(thread_id,request->>'thread_id','life:'||subject)=%s ORDER BY created_at LIMIT 1"
        ).format(repo.table("core_runs")),
        (owner, subject, thread),
    ).fetchone()


def queue_thread(
    service: Any,
    *,
    owner: str,
    subject: str,
    thread: str,
    sources: list[str],
    request_id: str,
    conversation_id: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    from mingjing_core.application.thread_inbox import ThreadInbox

    repo = service.repo
    if options.keys() & RESERVED_OPTIONS:
        raise EvidenceError("入站调用不能自行指定运行身份或来源")
    with repo.transaction(owner) as connection:
        rows = ingress_sources(repo, owner, subject, thread, sources)
        primary = rows[-1]
        previous = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE owner=%s AND operation_id=%s").format(repo.table("core_runs")),
            (owner, request_id),
        ).fetchone()
        parent = active_thread_run(repo, connection, owner, subject, thread) if previous is None else None
        submit = getattr(service, "_submit_validated", service.submit)
        run = submit(
            owner=owner,
            subject=subject,
            message=primary["content"],
            request_id=request_id,
            conversation_id=conversation_id,
            source_message_id=primary["id"],
            **options,
        )
        if previous is not None:
            _same_route(run, subject, thread, rows)
            return run
        runtime = owner_runtime(repo.assert_scope(owner, subject)["settings"])
        request = dict(
            run["request"],
            thread_id=thread,
            incognito=thread.startswith("incognito:"),
            source_message_ids=[row["id"] for row in rows],
            source_segments=source_segments(rows),
        )
        if parent is not None:
            request["inbox_parent_run_id"] = parent["id"]
        connection.execute(
            sql.SQL(
                "UPDATE {} SET runtime=%s,thread_id=%s,lane='interactive',kind='turn',request=%s,status=%s "
                "WHERE owner=%s AND id=%s AND status='queued' AND attempts=0 AND calls=0"
            ).format(repo.table("core_runs")),
            (runtime, thread, Jsonb(request), "inbox_wait" if parent else "queued", owner, run["id"]),
        )
        result = repo.fetch_run(owner, run["id"])
        ThreadInbox(repo).record(result, parent=parent)
        return result


def _same_route(run: dict[str, Any], subject: str, thread: str, sources: list[dict[str, Any]]) -> None:
    request = run["request"]
    actual = run.get("thread_id") or request.get("thread_id") or "life:" + run["subject"]
    identifiers = request.get("source_message_ids", [request.get("source_message_id")])
    if (
        run["subject"] != subject
        or actual != thread
        or identifiers != [source["id"] for source in sources]
        or request.get("incognito", False) != thread.startswith("incognito:")
    ):
        raise ScopeError("幂等运行身份与原人物、线程或来源不符")

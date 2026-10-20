"""Retire only authenticated private threads; all body-bearing run storage is scrubbed."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.timestamps import history_instant


def retire_private_thread(
    repo: PostgresRepository,
    owner: str,
    ident: str,
    *,
    subject: str = "self",
    expired_only: bool = True,
    clock: Clock | None = None,
) -> dict[str, Any]:
    clock = clock or get_clock()
    if not ident.startswith("incognito:"):
        raise EvidenceError("只允许清理无痕线程")
    with repo.transaction(owner) as connection:
        repo.assert_scope(owner, subject)
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("thread:" + owner + ":" + ident,))
        thread = repo.get(owner, "thread", ident, include_deleted=True)
        if thread["subject_id"] != subject:
            raise ScopeError("无痕线程不属于当前人物")
        if thread["status"] == "deleted":
            return {"retired": False, "runs": 0, "messages": 0}
        expiry = history_instant(thread.get("expires_at"))
        if expired_only and (expiry is None or expiry > clock.now()):
            return {"retired": False, "runs": 0, "messages": 0}
        if thread.get("mode") != "incognito":
            raise EvidenceError("不能将其他线程当作无痕清理")
        runs = [
            row["id"]
            for row in connection.execute(
                sql.SQL("SELECT id FROM {} WHERE owner=%s AND subject=%s AND thread_id=%s FOR UPDATE").format(
                    repo.table("core_runs")
                ),
                (owner, subject, ident),
            ).fetchall()
        ]
        messages = connection.execute(
            sql.SQL(
                "UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() "
                "WHERE owner=%s AND subject=%s AND kind='message' AND data->>'thread_id'=%s RETURNING id"
            ).format(repo.table("core_entities")),
            (owner, subject, ident),
        ).fetchall()
        _scrub_runs(repo, connection, owner, runs)
        connection.execute(
            sql.SQL(
                "UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() "
                "WHERE owner=%s AND subject=%s AND kind='thread' AND id=%s"
            ).format(repo.table("core_entities")),
            (owner, subject, ident),
        )
        repo.bump_revision(connection, owner, subject=subject, kind="thread")
        return {"retired": True, "runs": len(runs), "messages": len(messages)}


def _scrub_runs(repo: PostgresRepository, connection: Any, owner: str, runs: list[str]) -> None:
    if not runs:
        return
    connection.execute(
        sql.SQL(
            "UPDATE {} SET request='{{}}',result=NULL,checkpoint='{{}}',status='revoked',lease_token=NULL,"
            "lease_until=NULL,cancel_requested_at=now(),error='PRIVATE_THREAD_RETIRED',updated_at=now() "
            "WHERE owner=%s AND id=ANY(%s)"
        ).format(repo.table("core_runs")),
        (owner, runs),
    )
    connection.execute(
        sql.SQL(
            "UPDATE {} SET output=NULL,error_code='PRIVATE_THREAD_RETIRED' WHERE owner=%s AND run_id=ANY(%s)"
        ).format(repo.table("core_run_steps")),
        (owner, runs),
    )
    connection.execute(
        sql.SQL("UPDATE {} SET payload='{{}}' WHERE owner=%s AND run_id=ANY(%s)").format(repo.table("core_run_events")),
        (owner, runs),
    )
    connection.execute(
        sql.SQL(
            "UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() "
            "WHERE owner=%s AND data->>'run_id'=ANY(%s) "
            "AND kind IN ('runtime_step','artifact','interpretive_claim','note','proposal')"
        ).format(repo.table("core_entities")),
        (owner, runs),
    )

"""Bounded recovery makes dormant supplemental turns visible after their parent ends."""

from typing import Any

from psycopg import sql


def recover_inboxes(repo: Any, owner: str | None = None) -> int:
    from mingjing_core.application.thread_inbox import ThreadInbox

    with repo.transaction(owner) as connection:
        clause = sql.SQL(" AND owner=%s") if owner else sql.SQL("")
        rows = connection.execute(
            sql.SQL("SELECT DISTINCT owner FROM {} WHERE status='inbox_wait'").format(repo.table("core_runs"))
            + clause
            + sql.SQL(" ORDER BY owner LIMIT 100"),
            (owner,) if owner else (),
        ).fetchall()
    return sum(ThreadInbox(repo).recover(row["owner"])["queued"] for row in rows)

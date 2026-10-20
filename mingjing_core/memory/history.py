"""Bounded history windows retain original timestamp precision and old cursors."""

from __future__ import annotations

import heapq
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from psycopg import sql
from psycopg.rows import dict_row

from mingjing_core.timekit.timestamps import history_instant

from .private import is_private

if TYPE_CHECKING:
    from collections.abc import Iterator

    # Database history and run JSON have different schema-dependent value types.
    from typing import Any

    from mingjing_core.repositories.postgres import PostgresRepository


def sort_key(row: dict[str, Any]) -> tuple[datetime, str, int, str]:
    stamp = history_instant(row.get("at")) or history_instant(row.get("created_at")) or datetime.min.replace(tzinfo=UTC)
    role = str(row["role"])
    return stamp, str(row["turn_id"]), {"user": 0, "assistant": 1, "tool": 2, "legacy": 3}.get(role, 4), role


def _runs(repo: PostgresRepository, owner: str, subject: str, session: str) -> list[dict[str, Any]]:
    with repo.transaction(owner) as connection:
        rows = connection.execute(
            sql.SQL(
                "SELECT * FROM {} WHERE owner=%s AND subject=%s "
                "AND coalesce(thread_id,'') NOT LIKE 'incognito:%%' "
                "AND coalesce(request->>'incognito','false')<>'true' ORDER BY created_at,id"
            ).format(repo.table("core_runs")),
            (owner, subject),
        ).fetchall()
    return [row for row in rows if session in ("shared", "") or row["request"].get("conversation_id") == session]


def _messages(repo: PostgresRepository, owner: str, subject: str, session: str) -> Iterator[dict[str, Any]]:
    # No created_at cap: backfilled replies are created now but occurred years ago.
    # Stream every eligible candidate so pre-backfill rows with missing/invalid
    # at_ms retain their existing timestamp fallback. Only the final window is kept.
    with repo.transaction(owner) as connection:
        query = sql.SQL("""SELECT * FROM {} WHERE owner=%s AND subject=%s AND kind='message'
            AND status NOT IN ('deleted','hidden')""").format(repo.table("core_entities"))
        args = [owner, subject]
        if session not in ("shared", ""):
            query += sql.SQL(" AND data->>'conversation_id'=%s")
            args.append(session)
        query += sql.SQL(
            " ORDER BY CASE WHEN data->>'at_ms' ~ '^-?[0-9]{1,17}$' THEN (data->>'at_ms')::bigint "
            "END DESC NULLS LAST,id DESC"
        )
        with connection.cursor(name="history_" + uuid.uuid4().hex, row_factory=dict_row) as cursor:
            cursor.execute(query, args)
            while rows := cursor.fetchmany(256):
                for row in rows:
                    message = repo._decode(row)
                    if message.get("content") and not is_private(message):
                        yield dict(
                            message,
                            source=message.get("channel", "web"),
                            at=message.get("at", message["created_at"]),
                            turn_id=message.get("source_id", message["id"]),
                        )


def _attach_run(
    row: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_source: dict[str | None, dict[str, Any]],
    by_operation: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    run = None
    if row["role"] == "user":
        run = by_source.get(row["id"]) or by_operation.get(row["turn_id"])
        if run:
            row.update(
                turn_id=run["operation_id"],
                run_id=run["id"],
                status=run["status"],
                meta={
                    "meta": {"core_run": {"run_id": run["id"], "operation_id": run["operation_id"]}},
                    "error": run["error"],
                },
            )
    elif row["role"] == "assistant":
        run = by_id.get(row.get("run_id"))
        if run and run["status"] == "succeeded":
            row.update(turn_id=run["operation_id"], meta=run["result"])
    return run


def history_window(
    repo: PostgresRepository,
    owner: str,
    subject: str,
    session: str,
    limit: int,
    boundary: tuple[datetime, str, int, str] | None,
    query: str,
) -> list[dict[str, Any]]:
    repo.assert_scope(owner, subject)
    runs = _runs(repo, owner, subject, session)
    by_id = {row["id"]: row for row in runs}
    by_source = {row["request"].get("source_message_id"): row for row in runs}
    by_operation = {row["operation_id"]: row for row in runs}
    heap, stored = [], set()
    limit = max(1, min(int(limit), 500))

    def retain(row: dict[str, Any]) -> None:
        key = sort_key(row)
        if (boundary is not None and key >= boundary) or (query and query.lower() not in row["content"].lower()):
            return
        row["cursor"] = key[0].isoformat(timespec="microseconds") + "|" + str(row["turn_id"]) + "|" + row["role"]
        item = (key, str(row.get("id", row["cursor"])), row)
        if len(heap) < limit:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)

    for row in _messages(repo, owner, subject, session):
        run = _attach_run(row, by_id, by_source, by_operation)
        if row["role"] == "assistant" and run:
            stored.add(run["id"])
        retain(row)
    for run in runs:
        if run["status"] == "succeeded" and run["id"] not in stored:
            retain(
                {
                    "role": "assistant",
                    "content": run["result"]["answer"],
                    "at": run["updated_at"].isoformat(),
                    "turn_id": run["operation_id"],
                    "source": "web",
                    "meta": run["result"],
                }
            )
    return [item[2] for item in sorted(heap, key=lambda item: item[:2])]

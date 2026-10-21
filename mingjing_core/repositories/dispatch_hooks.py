"""Transaction-local v4 admission and body-free queue notifications."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from psycopg import sql

from mingjing_core.domain.contracts import LeaseConflict

if TYPE_CHECKING:
    from .postgres import PostgresRepository


def notify_run(connection: Any, schema: str, ident: str, *, cancel: bool = False) -> None:
    channel = "mj_run_cancel" if cancel else "mj_run_queued"
    connection.execute("SELECT pg_notify(%s,%s)", (channel, json.dumps({"schema": schema, "run_id": ident})))


def admit_v4(repo: PostgresRepository, connection: Any, row: dict[str, Any]) -> None:
    if row["runtime"] != "v4":
        return
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (repo.schema + ":dispatch-capacity",))
    capacity = repo.max_running if repo.max_running is not None else 3
    active = connection.execute(
        sql.SQL(
            "SELECT lane,count(*) AS n FROM {} WHERE runtime='v4' AND status='running' "
            "AND lease_until>now() AND id<>%s GROUP BY lane"
        ).format(repo.table("core_runs")),
        (row["id"],),
    ).fetchall()
    counts = {item["lane"]: item["n"] for item in active}
    lane_limit = 1 if row["lane"] == "background" else max(1, capacity - 1)
    if sum(counts.values()) >= capacity or counts.get(row["lane"], 0) >= lane_limit:
        raise LeaseConflict("调度通道容量已占用，原请求保留在队列")
    if row["cancel_requested_at"] is not None:
        raise LeaseConflict("本轮已请求停止，不能获取新租约")
    thread = row["thread_id"] or row["request"].get("thread_id") or "life:" + row["subject"]
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        (repo.schema + ":thread:" + row["owner"] + ":" + thread,),
    )
    other = connection.execute(
        sql.SQL(
            "SELECT 1 FROM {} WHERE owner=%s AND runtime='v4' AND status='running' AND lease_until>now() "
            "AND id<>%s AND coalesce(thread_id,request->>'thread_id','life:'||subject)=%s LIMIT 1"
        ).format(repo.table("core_runs")),
        (row["owner"], row["id"], thread),
    ).fetchone()
    if other:
        raise LeaseConflict("同一线程已有运行中的轮次，原请求保留在队列")

"""Bounded lane scans delegate every admission decision to the common PG fence."""

from __future__ import annotations

from typing import Any, Literal

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock

Lane = Literal["interactive", "background"]


class DispatcherClaims:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo
        if repo.max_running is not None and repo.max_running < 3:
            raise EvidenceError("双通道调度需要至少三个全局容量，请显式配置 CORE_RUN_CONCURRENCY")

    def recover(self) -> int:
        with self.repo.transaction() as connection:
            return connection.execute(
                sql.SQL(
                    "UPDATE {} SET status=CASE WHEN cancel_requested_at IS NOT NULL THEN 'cancelled' "
                    "WHEN deadline_at<=%s THEN 'failed' ELSE 'queued' END,lease_token=NULL,lease_until=NULL,"
                    "updated_at=now() WHERE runtime='v4' AND ((status='running' AND lease_until<=now()) "
                    "OR (status='queued' AND (cancel_requested_at IS NOT NULL OR deadline_at<=%s)))"
                ).format(self.repo.table("core_runs")),
                (get_clock().now(), get_clock().now()),
            ).rowcount

    def claim(self, lane: Lane) -> dict[str, Any] | None:
        if lane not in {"interactive", "background"}:
            raise EvidenceError("调度通道无效")
        with self.repo.transaction() as connection:
            active = connection.execute(
                sql.SQL(
                    "SELECT lane,count(*) AS n FROM {} WHERE runtime='v4' AND status='running' "
                    "AND lease_until>now() GROUP BY lane"
                ).format(self.repo.table("core_runs"))
            ).fetchall()
            counts = {row["lane"]: row["n"] for row in active}
            capacity = self.repo.max_running if self.repo.max_running is not None else 3
            lane_limit = 1 if lane == "background" else capacity - 1
            if sum(counts.values()) >= capacity or counts.get(lane, 0) >= lane_limit:
                return None
            rows = connection.execute(
                sql.SQL(
                    "SELECT q.owner,q.id FROM {runs} q WHERE q.runtime='v4' AND q.lane=%s AND q.status='queued' "
                    "AND q.cancel_requested_at IS NULL AND (q.deadline_at IS NULL OR q.deadline_at>%s) "
                    "AND NOT EXISTS(SELECT 1 FROM {runs} a WHERE a.owner=q.owner AND a.runtime='v4' "
                    "AND a.status='running' AND a.lease_until>now() AND "
                    "coalesce(a.thread_id,a.request->>'thread_id','life:'||a.subject)="
                    "coalesce(q.thread_id,q.request->>'thread_id','life:'||q.subject)) "
                    "ORDER BY q.created_at,q.id LIMIT 100"
                ).format(runs=self.repo.table("core_runs")),
                (lane, get_clock().now()),
            ).fetchall()
        for row in rows:
            try:
                return self.repo.claim_run(row["owner"], row["id"], lease_seconds=150)
            except LeaseConflict:
                continue
        return None

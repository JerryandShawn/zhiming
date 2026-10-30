"""Explicit, bounded event cleanup. Importing or constructing it schedules nothing."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories import event_retention_metadata as metadata
from mingjing_core.timekit.clock import get_clock


class EventRetentionSweep:
    def __init__(self, repo: Any) -> None:
        self.repo = repo

    def tick(self, *, limit: int = 50, event_limit: int = 1000) -> dict[str, int]:
        if (
            type(limit) is not int
            or not 1 <= limit <= 50
            or type(event_limit) is not int
            or not 1 <= event_limit <= 1000
        ):
            raise EvidenceError("事件清理批量上限无效")
        counts = {
            "runs": 0,
            "events": 0,
            "tombstones": 0,
            "legacy_skipped": 0,
            "closed": 0,
        }
        remaining = event_limit
        for owner, ident in self._candidates(limit):
            if remaining <= 0:
                break
            result = self._one(owner, ident, remaining)
            for key, value in result.items():
                counts[key] += value
            remaining -= result["events"] + result["tombstones"]
        return counts

    def _candidates(self, limit: int) -> list[tuple[str, str]]:
        cutoff = (metadata.now() - timedelta(days=30)).isoformat()
        delta_cutoff = (metadata.now() - timedelta(hours=24)).isoformat()
        with self.repo.transaction() as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT owner,id FROM {} r WHERE runtime='v4' "
                    "AND status IN ('succeeded','failed','stale','cancelled','revoked') "
                    "AND coalesce(usage->%s->>'cleanup_complete','false')!='true' "
                    "AND (usage->%s->'terminal' IS NULL OR usage->%s->'terminal'->>'at'<=%s "
                    "OR (usage->%s->'terminal'->>'at'<=%s AND EXISTS(SELECT 1 FROM {} e "
                    "WHERE e.owner=r.owner AND e.run_id=r.id "
                    "AND e.kind='text_delta' AND e.payload!='{{}}'::jsonb))) "
                    "ORDER BY (usage->%s->'terminal' IS NULL),id LIMIT %s"
                ).format(self.repo.table("core_runs"), self.repo.table("core_run_events")),
                (metadata.KEY, metadata.KEY, metadata.KEY, cutoff, metadata.KEY, delta_cutoff, metadata.KEY, limit),
            ).fetchall()
        return [(row["owner"], row["id"]) for row in rows]

    def _one(self, owner: str, ident: str, limit: int) -> dict[str, int]:
        result = {
            "runs": 0,
            "events": 0,
            "tombstones": 0,
            "legacy_skipped": 0,
            "closed": 0,
        }
        with self.repo.transaction() as connection:
            raw = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE SKIP LOCKED").format(
                    self.repo.table("core_runs")
                ),
                (owner, ident),
            ).fetchone()
            if not raw or raw["runtime"] != "v4" or raw["status"] not in metadata.TERMINAL:
                return result
            run = self.repo._run(raw)
            if run["lease_token"] is not None or run["lease_until"] is not None:
                return result
            anchor = metadata.terminal_anchor(run) or (
                metadata.state(run)["closed"] if metadata.is_closed(run) else None
            )
            if anchor is None:
                result["legacy_skipped"] = 1
                return result
            age = get_clock().now() - metadata.instant(anchor["at"])
            if age < timedelta(hours=24):
                return result
            complete = age >= timedelta(days=30)
            value = metadata.state(run)
            # Persist the real maximum sequence before any delete, so a later append can never reuse a number.
            actual = metadata.actual_maximum(self.repo, connection, run)
            if value["high_watermark"] < actual:
                value["high_watermark"] = actual
                metadata.store(self.repo, connection, run, value)
            if complete and not metadata.is_closed(run):
                value["closed"] = dict(anchor)
                metadata.store(self.repo, connection, run, value)
                result["closed"] = 1
            rows = self._rows(connection, run, complete, limit)
            for row in rows:
                if not complete:
                    metadata.attest_deleted(self.repo, connection, run, row, anchor)
                connection.execute(
                    sql.SQL("DELETE FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
                        self.repo.table("core_run_events")
                    ),
                    (owner, ident, row["seq"]),
                )
            result["runs"], result["events"] = 1, len(rows)
            if complete:
                result["tombstones"] = metadata.prune_tombstones(self.repo, connection, run, limit - len(rows))
                if not self._rows(connection, run, True, 1) and result["tombstones"] < limit - len(rows):
                    value["cleanup_complete"] = True
                    metadata.store(self.repo, connection, run, value)
        return result

    def _rows(self, connection: Any, run: dict[str, Any], complete: bool, limit: int) -> list[dict[str, Any]]:
        return connection.execute(
            sql.SQL(
                "SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s AND payload!='{{}}'::jsonb "
                "AND (%s OR kind='text_delta') ORDER BY seq LIMIT %s FOR UPDATE"
            ).format(self.repo.table("core_run_events")),
            (run["owner"], run["id"], complete, limit),
        ).fetchall()

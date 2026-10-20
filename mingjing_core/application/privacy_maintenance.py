"""Bounded local retention; public replies and long-term facts remain available."""

from datetime import timedelta

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.incognito_reminders import IncognitoReminderService
from mingjing_core.application.private_retention import retire_private_thread
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.timekit.clock import get_clock
from mingjing_core.timekit.timestamps import history_instant


class PrivacyMaintenance:
    def __init__(self, repo):
        self.repo = repo

    def tick(self, *, limit: int = 50) -> dict[str, int]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise EvidenceError("保留策略批量上限无效")
        counts = {"private_threads": 0, "reminders": 0, "private_steps": 0}
        for row in self._private_threads(limit):
            expiry = history_instant(row["expires_at"])
            if expiry is not None and expiry <= get_clock().now():
                result = retire_private_thread(self.repo, row["owner"], row["id"], subject=row["subject"])
                counts["private_threads"] += int(result["retired"])
        for owner in self._reminder_owners(limit):
            counts["reminders"] += IncognitoReminderService(self.repo).cleanup_delivered(owner)
        counts["private_steps"] = self._old_steps(limit)
        return counts

    def _private_threads(self, limit):
        with self.repo.transaction() as connection:
            return connection.execute(sql.SQL(
                "SELECT owner,id,subject,data->>'expires_at' AS expires_at FROM {} "
                "WHERE kind='thread' AND status='active' AND data->>'mode'='incognito' "
                "ORDER BY data->>'expires_at',id LIMIT %s"
            ).format(self.repo.table("core_entities")), (limit,)).fetchall()

    def _reminder_owners(self, limit):
        with self.repo.transaction() as connection:
            rows = connection.execute(sql.SQL(
                "SELECT DISTINCT owner FROM {} WHERE kind='reminder' AND status='active' "
                "AND data->>'source'='incognito_explicit' ORDER BY owner LIMIT %s"
            ).format(self.repo.table("core_entities")), (limit,)).fetchall()
        return [row["owner"] for row in rows]

    def _old_steps(self, limit):
        with self.repo.transaction() as connection:
            rows = connection.execute(sql.SQL(
                "SELECT owner,id,usage FROM {} WHERE runtime='v4' "
                "AND status IN ('succeeded','failed','cancelled','stale','revoked') AND updated_at<%s "
                "AND usage->'agent_runtime'->>'private_steps_expired_at' IS NULL "
                "ORDER BY updated_at,id LIMIT %s FOR UPDATE SKIP LOCKED"
            ).format(self.repo.table("core_runs")), (get_clock().now()-timedelta(days=30), limit)).fetchall()
            for row in rows:
                self._clear(connection, row)
        return len(rows)

    def _clear(self, connection, row):
        connection.execute(sql.SQL(
            "UPDATE {} SET output=NULL,error_code='PRIVATE_STEP_EXPIRED' WHERE owner=%s AND run_id=%s"
        ).format(self.repo.table("core_run_steps")), (row["owner"], row["id"]))
        connection.execute(sql.SQL(
            "UPDATE {} SET data='{{}}',status='deleted',revision=revision+1,updated_at=now() "
            "WHERE owner=%s AND kind='runtime_step' AND data->>'run_id'=%s AND status!='deleted'"
        ).format(self.repo.table("core_entities")), (row["owner"], row["id"]))
        usage = dict(row["usage"])
        usage["agent_runtime"] = dict(usage.get("agent_runtime", {}),
                                      private_steps_expired_at=get_clock().now().isoformat())
        connection.execute(sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(
            self.repo.table("core_runs")), (Jsonb(usage), row["owner"], row["id"]))

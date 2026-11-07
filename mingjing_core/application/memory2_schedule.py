"""Registered, bounded local memory maintenance; all reflection is scripted."""

import logging
import threading
import time

from psycopg import sql

from mingjing_core.application.memory2_background_archive import MemoryArchiveSweep
from mingjing_core.application.memory2_background_reflection import IdleMemoryReflection
from mingjing_core.timekit.clock import get_clock

LOG = logging.getLogger(__name__)


class MemoryMaintenanceSchedule:
    def __init__(self, repo, *, clock=None, monotonic=time.monotonic):
        self.repo, self.clock, self.monotonic = repo, clock or get_clock(), monotonic
        self.archive = MemoryArchiveSweep(repo, self.clock)
        self.reflection = IdleMemoryReflection(repo, self.clock)
        self.next_due, self.cursor = 0.0, ""
        self.guard = threading.Lock()

    def tick(self):
        if not self.guard.acquire(blocking=False):
            return None
        try:
            now = self.monotonic()
            if now < self.next_due:
                return None
            self.next_due = now + 60
            return self._sweep()
        except Exception:
            LOG.warning("MEMORY_MAINTENANCE_FAILED")
            return {"status": "failed", "code": "MEMORY_MAINTENANCE_FAILED"}
        finally:
            self.guard.release()

    def _sweep(self):
        with self.repo.transaction() as connection:
            owners = connection.execute(
                sql.SQL("SELECT id FROM {} WHERE id>%s ORDER BY id LIMIT 50").format(self.repo.table("core_owners")),
                (self.cursor,),
            ).fetchall()
        if not owners:
            self.cursor = ""
            return {"status": "succeeded", "archived": 0, "reflections": 0}
        archived, reflected = 0, 0
        for row in owners:
            owner = row["id"]
            archived += self.archive.owner(owner)["archived"]
            with self.repo.transaction(owner) as connection:
                threads = connection.execute(
                    sql.SQL(
                        "SELECT id,subject FROM {} WHERE owner=%s AND kind='thread' AND status='active' "
                        "AND data->>'mode'='life' AND data->'incognito'='false'::jsonb ORDER BY id LIMIT 50"
                    ).format(self.repo.table("core_entities")),
                    (owner,),
                ).fetchall()
            for thread in threads:
                reflected += self.reflection.thread(owner, thread["id"], thread["subject"]) == "completed"
        self.cursor = owners[-1]["id"]
        return {"status": "succeeded", "archived": archived, "reflections": reflected}

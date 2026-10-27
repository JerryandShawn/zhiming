"""Bounded 03:00 owner-local catch-up using existing archive authority and storage."""

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg import sql

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_archive import MemoryArchiveService
from mingjing_core.domain.contracts import CoreError, ScopeError
from mingjing_core.memory2.expiration import archive_deadline
from mingjing_core.repositories.postgres import fingerprint


def marker(repo, owner, ident):
    try:
        return repo.get(owner, "runtime_step", ident, include_deleted=True)
    except ScopeError:
        return None


class MemoryArchiveSweep:
    def __init__(self, repo, clock):
        self.repo, self.clock = repo, clock
        self.service = MemoryArchiveService(V4FactMemory(repo), clock=clock)

    def owner(self, owner):
        with self.repo.transaction(owner) as connection:
            settings = self.repo.assert_scope(owner)["settings"]
            try:
                local = self.clock.now().astimezone(ZoneInfo(settings.get("timezone", "Asia/Shanghai")))
            except (ValueError, TypeError, ZoneInfoNotFoundError):
                return {"archived": 0, "skipped": 1}
            if local.hour < 3:
                return {"archived": 0, "skipped": 0}
            ident = "memory2-archive-day-" + fingerprint([owner, str(local.date())])[:32]
            old = marker(self.repo, owner, ident)
            if old and (old["status"] == "deleted" or old.get("done")):
                return {"archived": 0, "skipped": 0}
            rows = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE owner=%s AND kind='fact' AND status='active' AND id>%s ORDER BY id LIMIT 100"
                ).format(self.repo.table("core_entities")),
                (owner, old.get("cursor", "") if old else ""),
            ).fetchall()
            counts = {"archived": 0, "skipped": 0}
            for raw in rows:
                row = self.repo._decode(raw)
                deadline = archive_deadline(row)
                if deadline is None or deadline > self.clock.now():
                    continue
                try:
                    self.service.archive(
                        owner,
                        row["subject_id"],
                        row["id"],
                        expected_revision=row["revision"],
                        operation_id=ident + ":" + row["id"],
                    )
                    counts["archived"] += 1
                except CoreError:
                    counts["skipped"] += 1
            self.repo.put(
                owner,
                "runtime_step",
                ident,
                {
                    "task": "memory2_archive",
                    "done": len(rows) < 100,
                    "cursor": rows[-1]["id"] if rows else "",
                    "local_day": str(local.date()),
                },
                expected_revision=old["revision"] if old else 0,
                operation_id=ident + ":page",
            )
            return counts

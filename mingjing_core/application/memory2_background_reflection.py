"""Idle reflection uses a local extractive script, with no provider or model factory."""

from datetime import timedelta

from psycopg import sql

from mingjing_core.application.agent_tools_policy import V4FactMemory
from mingjing_core.application.memory2_background_archive import marker
from mingjing_core.application.memory2_profile_reflection import ProfileReflectionService
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict
from mingjing_core.memory.private import is_private
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.timestamps import history_instant


class ScriptedReflectionModel:
    """Copy authorized original text into pending suggestions, never infer user facts."""

    def complete(self, snapshot):
        return [
            {
                "op": "add",
                "section": row["suggested_section"],
                "text": row["text"],
                "source_ids": row["source_ids"],
                "confidence": 1.0,
            }
            for row in snapshot["facts"][:20]
            if 1 <= len(row["text"]) <= 800
        ]


class IdleMemoryReflection:
    def __init__(self, repo, clock, *, model=None):
        self.repo, self.clock = repo, clock
        self.memory = V4FactMemory(repo)
        self.profiles = ProfileReflectionService(self.memory)
        self.model = model or ScriptedReflectionModel()

    def thread(self, owner, ident, subject):
        key = self.repo.schema + ":memory2-reflection:" + owner + ":" + ident
        with self.repo.pool.connection() as connection:
            locked = connection.execute("SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok", (key,)).fetchone()
            if not locked["ok"]:
                return "busy"
            try:
                return self._run(owner, ident, subject)
            finally:
                connection.execute("SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,))

    def _ready(self, owner, ident, subject):
        row = ThreadService(self.repo, clock=self.clock).get(owner, ident, subject=subject)
        at = history_instant(row.get("last_activity_at"))
        if row.get("mode") != "life" or row.get("incognito") is not False or ident != "life:" + subject:
            raise EvidenceError("仅长期线程参与反思")
        if at is None or self.clock.now() - at < timedelta(minutes=10):
            raise EvidenceError("线程尚未空闲十分钟")
        with self.repo.transaction(owner) as connection:
            active = connection.execute(
                sql.SQL(
                    "SELECT 1 FROM {} WHERE owner=%s AND status IN ('queued','running') "
                    "AND (request->>'thread_id'=%s OR (subject=%s AND request->>'thread_id' IS NULL)) LIMIT 1"
                ).format(self.repo.table("core_runs")),
                (owner, ident, subject),
            ).fetchone()
        if active:
            raise EvidenceError("线程仍有在途请求")
        return row

    def _prepare(self, owner, ident, subject):
        thread = self._ready(owner, ident, subject)
        facts = self.memory.facts(owner, subject)
        selected = []
        for row in facts:
            sources = [self.memory.get_source(owner, ref["message_id"]) for ref in row.get("source_refs", [])]
            if sources and all(not is_private(source) and source.get("thread_id") == ident for source in sources):
                selected.append(row["id"])
        if not selected:
            return None
        snapshot = self.profiles.prepare(owner, subject, sorted(selected)[:100])
        job = (
            "memory2-reflect-" + fingerprint([owner, ident, thread["last_activity_at"], snapshot["fact_versions"]])[:32]
        )
        if marker(self.repo, owner, job):
            return None
        record = self.repo.put(
            owner,
            "runtime_step",
            job,
            {
                "task": "memory2_reflection",
                "state": "running",
                "thread_id": ident,
                "activity": thread["last_activity_at"],
                "fact_ids": list(snapshot["fact_versions"]),
            },
            subject=subject,
            expected_revision=0,
            operation_id=job,
        )
        return record, snapshot

    def _run(self, owner, ident, subject):
        with self.repo.transaction(owner):
            try:
                prepared = self._prepare(owner, ident, subject)
            except CoreError:
                return "ineligible"
        if prepared is None:
            return "unchanged"
        record, snapshot = prepared
        try:
            ops = self.model.complete(snapshot)
            with self.repo.transaction(owner):
                current = self._ready(owner, ident, subject)
                if current["last_activity_at"] != record["activity"]:
                    raise RevisionConflict("反思期间线程已有新消息")
                receipt = (
                    self.profiles.consume_patch(
                        owner,
                        subject,
                        ops,
                        fact_versions=snapshot["fact_versions"],
                        operation_id=record["id"] + ":proposals",
                    )
                    if ops
                    else None
                )
                self.repo.update(
                    owner,
                    "runtime_step",
                    record["id"],
                    {"state": "completed", "ids": receipt["ids"] if receipt else []},
                    expected_revision=record["revision"],
                )
            return "completed"
        except Exception:
            with self.repo.transaction(owner):
                current = self.repo.get(owner, "runtime_step", record["id"], include_deleted=True)
                if current["status"] != "deleted":
                    self.repo.update(
                        owner,
                        "runtime_step",
                        current["id"],
                        {"state": "failed", "code": "MEMORY_REFLECTION_FAILED"},
                        expected_revision=current["revision"],
                    )
            return "failed"

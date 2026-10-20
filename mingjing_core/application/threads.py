"""Owner-bound life/private threads; private bodies have explicit expiry and no FTS."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import sql

from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.memory.private import is_private
from mingjing_core.memory.threads import project_sources
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.timestamps import history_instant


class ThreadService:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.memory, self.clock = repo, MemoryService(repo), clock or get_clock()

    def create(self, owner: str, *, subject: str = "self", incognito: bool = False, request_id: str) -> dict[str, Any]:
        if type(incognito) is not bool or not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise EvidenceError("线程需要稳定请求标识与明确模式")
        ident = "incognito:" + fingerprint([owner, subject, request_id])[:32] if incognito else "life:" + subject
        with self.repo.transaction(owner) as connection:
            self.repo.assert_scope(owner, subject)
            self._lock(connection, owner, ident)
            try:
                return self.get(owner, ident, subject=subject)
            except ScopeError:
                pass
            now = self.clock.now()
            return self.repo.put(
                owner,
                "thread",
                ident,
                dict(
                    mode="incognito" if incognito else "life",
                    incognito=incognito,
                    last_activity_at=now.isoformat(),
                    expires_at=(now + timedelta(hours=24)).isoformat() if incognito else None,
                ),
                subject=subject,
                expected_revision=0,
                operation_id="thread-create:" + fingerprint([owner, request_id]),
            )

    @staticmethod
    def _lock(connection: Any, owner: str, ident: str) -> None:
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", ("thread:" + owner + ":" + ident,))

    def get(self, owner: str, ident: str, *, subject: str = "self") -> dict[str, Any]:
        self.repo.assert_scope(owner, subject)
        row = self.repo.get(owner, "thread", ident)
        if row["subject_id"] != subject or row["status"] != "active":
            raise ScopeError("线程不属于当前人物或已关闭")
        if ident != "life:" + subject and (not ident.startswith("incognito:") or row.get("mode") != "incognito"):
            raise ScopeError("线程模式无效")
        if row.get("mode") == "incognito":
            expiry = history_instant(row.get("expires_at"))
            if expiry is None or expiry <= self.clock.now():
                raise EvidenceError("无痕线程已到期，请开始新线程")
        return row

    def touch(self, owner: str, ident: str, *, subject: str = "self") -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            self._lock(connection, owner, ident)
            row = self.get(owner, ident, subject=subject)
            now = self.clock.now()
            updates = {"last_activity_at": now.isoformat()}
            if row.get("mode") == "incognito":
                updates["expires_at"] = (now + timedelta(hours=24)).isoformat()
            return self.repo.update(owner, "thread", ident, updates, expected_revision=row["revision"])

    def receive(
        self,
        owner: str,
        ident: str,
        text: str,
        *,
        request_id: str,
        subject: str = "self",
        channel: str = "web",
        external_id: str | None = None,
        conversation_id: str = "shared",
        at: datetime | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 200:
            raise EvidenceError("消息需要稳定请求标识")
        if at is not None and (not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None):
            raise EvidenceError("原话时间必须是带时区的时刻")
        with self.repo.transaction(owner) as connection:
            self._lock(connection, owner, ident)
            thread = self.get(owner, ident, subject=subject)
            stable_source = source_id if source_id is not None else "thread-source:" + fingerprint([ident, request_id])
            existed = self._existing_source(owner, ident, channel, stable_source)
            row = self.memory.receive(
                owner,
                subject,
                text,
                source_id=stable_source,
                channel=channel,
                external_id=external_id,
                conversation_id=conversation_id,
                at=at or self.clock.now(),
            )
            if thread.get("mode") == "incognito":
                if row.get("thread_id") not in {"life:" + subject, ident}:
                    raise ScopeError("原始消息不能移到其他线程")
                if row.get("thread_id") != ident:
                    row = self.repo.update(
                        owner,
                        "message",
                        row["id"],
                        {"thread_id": ident, "incognito": True, "policy": dict(row["policy"], persist_allowed=False)},
                        expected_revision=row["revision"],
                    )
            if not existed:
                self.touch(owner, ident, subject=subject)
            return row

    def _existing_source(self, owner: str, ident: str, channel: str, source_id: str) -> bool:
        if not isinstance(source_id, str) or not 1 <= len(source_id) <= 200:
            raise EvidenceError("消息需要有效来源标识")
        message_id = "msg_" + fingerprint([owner, channel, source_id, "user"])[:32]
        try:
            original = self.repo.get(owner, "message", message_id, include_deleted=True)
        except ScopeError:
            return False
        if original["status"] == "deleted" or self.repo.is_revoked(owner, "message", message_id):
            raise EvidenceError("已撤销的原话不能重新导入")
        if original.get("thread_id") != ident:
            raise ScopeError("已存在的原话不能移到其他线程")
        return True

    def history(
        self, owner: str, ident: str, *, subject: str = "self", limit: int = 80, through: str | None = None
    ) -> list[dict[str, Any]]:
        self.get(owner, ident, subject=subject)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise EvidenceError("线程历史数量无效")
        boundary = (None, None, None)
        if through is not None:
            source = self.memory.get_source(owner, through, for_context=True)
            if source["subject_id"] != subject or source.get("thread_id") != ident or source["status"] != "active":
                raise ScopeError("历史边界不属于当前有效线程")
            boundary = (source["at_ms"], source["created_at"], source["id"])
        with self.repo.transaction(owner) as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE owner=%s AND subject=%s AND kind='message' AND status='active' "
                    "AND data->>'thread_id'=%s AND (%s::bigint IS NULL OR "
                    "((data->>'at_ms')::bigint,created_at,id)<= (%s,%s::timestamptz,%s)) "
                    "ORDER BY (data->>'at_ms')::bigint DESC,created_at DESC,id DESC LIMIT %s"
                ).format(self.repo.table("core_entities")),
                (owner, subject, ident, boundary[0], *boundary, limit),
            ).fetchall()
        sources = [self.memory.get_source(owner, row["id"], for_context=True) for row in reversed(rows)]
        return project_sources(
            self.memory, owner, sources, [], set(), private_thread=ident if ident.startswith("incognito:") else None
        )

    def record_private_reply(self, owner: str, run: dict[str, Any], text: str, **lineage: Any) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            current = self.repo._leased(connection, owner, run["id"], run["lease_token"])
            if (
                current["runtime"] != "v4"
                or current["retry_epoch"] != run["retry_epoch"]
                or current["cancel_requested_at"]
            ):
                raise EvidenceError("无痕回答运行已失效")
            if current["deadline_at"] is not None and current["deadline_at"] <= self.clock.now():
                raise EvidenceError("无痕回答执行超时")
            return self._record_private_reply(owner, self.repo._run(current), text, **lineage)

    def _record_private_reply(
        self, owner: str, run: dict[str, Any], text: str, *, source_ids=None, used_fact_ids=(), used_claim_ids=()
    ) -> dict[str, Any]:
        ident, subject = run["thread_id"], run["subject"]
        self.get(owner, ident, subject=subject)
        if not ident.startswith("incognito:") or not text.strip() or len(text) > 200_000:
            raise EvidenceError("无痕回答结构无效")
        source = self.memory.get_source(owner, run["request"]["source_message_id"])
        if source.get("thread_id") != ident or not is_private(source):
            raise ScopeError("无痕回答来源不符")
        lineage = self._reply_lineage(owner, run, source, source_ids, used_fact_ids, used_claim_ids)
        message_id = "msg_" + fingerprint([owner, "assistant", run["id"]])[:32]
        try:
            old = self.repo.get(owner, "message", message_id, include_deleted=True)
        except ScopeError:
            old = None
        if old:
            if old["status"] != "active" or old.get("content") != text or old.get("thread_id") != ident:
                raise EvidenceError("无痕回答不能覆盖旧稿或撤销内容")
            return old
        now = self.clock.now()
        return self.repo.put(
            owner,
            "message",
            message_id,
            dict(
                content=text,
                role="assistant",
                channel=source["channel"],
                at=now.isoformat(),
                at_ms=int(now.timestamp() * 1000),
                thread_id=ident,
                incognito=True,
                run_id=run["id"],
                **lineage,
                case_ids=[],
                policy={"origin": "system", "run_context": False, "persist_allowed": False},
            ),
            subject=subject,
            expected_revision=0,
            operation_id="private-assistant:" + run["id"],
        )

    def _reply_lineage(self, owner, run, source, source_ids, used_fact_ids, used_claim_ids):
        sources = list(dict.fromkeys(source_ids or [source["id"]]))
        for linked in sources:
            original = self.memory.get_source(owner, linked)
            if (
                original["subject_id"] != run["subject"]
                or original["status"] != "active"
                or original.get("thread_id") not in {run["thread_id"], "life:" + run["subject"]}
                or source_ids is not None
                and run["state_version"].get("message:" + linked) != original["revision"]
            ):
                raise EvidenceError("无痕回答来源未获本轮有效依赖授权")
        for kind, identifiers in (("fact", used_fact_ids), ("interpretive_claim", used_claim_ids)):
            for linked in identifiers:
                row = self.repo.get(owner, kind, linked)
                if (
                    row["subject_id"] != run["subject"]
                    or run["state_version"].get(kind + ":" + linked) != row["revision"]
                ):
                    raise EvidenceError("无痕回答引用不在本轮已核依赖中")
        return dict(source_ids=sources, used_fact_ids=list(used_fact_ids), used_claim_ids=list(used_claim_ids))

"""Durable fixed-window intake; callbacks neither call models nor send messages."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import sql

from mingjing_core.application.thread_inbox import ThreadInbox
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.thread_sources import ingress_sources
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.timestamps import history_instant


class FeishuIngress:
    def __init__(self, service: Any, *, clock: Clock | None = None) -> None:
        self.service, self.repo, self.clock = service, service.repo, clock or get_clock()
        self.threads, self.ingress = (
            ThreadService(self.repo, clock=self.clock),
            ThreadIngress(service, clock=self.clock),
        )

    def receive(
        self, *, owner: str, subject: str, author: str, chat_id: str, message_id: str, text: str, at: datetime | None
    ) -> dict[str, Any]:
        self._binding(owner, subject, author)
        if not isinstance(message_id, str) or not 1 <= len(message_id) <= 200:
            raise EvidenceError("飞书原话需要稳定消息标识")
        with self.repo.transaction(owner):
            thread = self._life_thread(owner, subject)
            operation = "feishu:message:" + message_id
            source = self.ingress.receive(
                owner=owner,
                subject=subject,
                thread_id=thread["id"],
                message=text,
                request_id=operation,
                source_id=message_id,
                channel="feishu",
                external_id=author,
                conversation_id="feishu:p2p:" + chat_id,
                at=at,
            )
            self._assert_time(source, at)
            thread = self.threads.get(owner, source["thread_id"], subject=subject)
            ident = "feishu-inbound:" + fingerprint([owner, message_id])[:32]
            try:
                old = self.repo.get(owner, "request", ident)
            except ScopeError:
                old = None
            if old is not None:
                if (old.get("source_id"), old.get("target"), old.get("chat_id"), old["subject_id"]) != (
                    source["id"],
                    author,
                    chat_id,
                    subject,
                ):
                    raise EvidenceError("飞书消息标识不能替换原始会话与作者")
                return self._accepted(old)
            batch = self._batch(owner, subject, thread["id"], author, chat_id)
            item = self.repo.put(
                owner,
                "request",
                ident,
                dict(
                    gateway="feishu",
                    source_id=source["id"],
                    source_ids=[source["id"]],
                    target=author,
                    business_id=operation,
                    chat_id=chat_id,
                    thread_id=thread["id"],
                    batch_id=batch["id"],
                    run_id=None,
                    delivery_status="pending",
                ),
                subject=subject,
                expected_revision=0,
                operation_id="feishu-accept:" + message_id,
            )
            self._attach(batch, source["id"], ident)
            return self._accepted(item)

    def _life_thread(self, owner: str, subject: str) -> dict[str, Any]:
        return self.threads.create(owner, subject=subject, request_id="feishu-life-thread:" + fingerprint(subject)[:32])

    @staticmethod
    def _assert_time(source: dict[str, Any], at: datetime | None) -> None:
        if at is not None and history_instant(source.get("at")) != at:
            raise EvidenceError("飞书消息标识不能替换原始时间")

    def _binding(self, owner: str, subject: str, author: str) -> None:
        binding = self.repo.resolve_channel("feishu", author)
        if binding["owner"] != owner or binding["subject"] != subject or binding.get("binding_kind") != "user":
            raise ScopeError("飞书原始作者没有当前人物的用户绑定")

    @staticmethod
    def _accepted(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "accepted",
            "owner": item["owner_user_id"],
            "inbound_id": item["id"],
            "run_id": item["run_id"],
        }

    def _batch(self, owner: str, subject: str, thread: str, author: str, chat: str) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            row = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE owner=%s AND subject=%s AND kind='request' AND status='active' "
                    "AND data->>'ingress'='feishu_batch' AND data->>'batch_state'='buffering' "
                    "AND data->>'target'=%s AND data->>'chat_id'=%s AND data->>'thread_id'=%s "
                    "ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE"
                ).format(self.repo.table("core_entities")),
                (owner, subject, author, chat, thread),
            ).fetchone()
        if row is not None:
            batch = self.repo._decode(row)
            if self.clock.now() < history_instant(batch["due_at"]):
                return batch
            self._flush(batch)
        now = self.clock.now()
        ident = "feishu-batch:" + fingerprint([owner, subject, thread, author, chat, now.isoformat()])[:32]
        return self.repo.put(
            owner,
            "request",
            ident,
            dict(
                ingress="feishu_batch",
                batch_state="buffering",
                target=author,
                chat_id=chat,
                thread_id=thread,
                first_received_at=now.isoformat(),
                due_at=(now + timedelta(milliseconds=2500)).isoformat(),
                source_ids=[],
                inbound_ids=[],
                run_id=None,
            ),
            subject=subject,
            expected_revision=0,
            operation_id=ident,
        )

    def _attach(self, batch: dict[str, Any], source: str, inbound: str) -> None:
        if len(batch["source_ids"]) >= 64:
            raise EvidenceError("飞书当前合并窗口已满，请稍后重试原消息")
        self.repo.update(
            batch["owner_user_id"],
            "request",
            batch["id"],
            dict(source_ids=[*batch["source_ids"], source], inbound_ids=[*batch["inbound_ids"], inbound]),
            expected_revision=batch["revision"],
        )

    def flush(self, owner: str, inbound_id: str) -> dict[str, Any]:
        with self.repo.transaction(owner):
            item = self.repo.get(owner, "request", inbound_id)
            if item.get("gateway") != "feishu":
                raise ScopeError("入口记录不是飞书原始事件")
            if item.get("run_id"):
                run = self.repo.fetch_run(owner, item["run_id"])
                return {"status": run["status"], "run_id": run["id"]}
            batch = self.repo.get(owner, "request", item["batch_id"])
            if batch["subject_id"] != item["subject_id"] or inbound_id not in batch["inbound_ids"]:
                raise ScopeError("飞书原话与合并批次不符")
            ingress_sources(self.repo, owner, batch["subject_id"], batch["thread_id"], batch["source_ids"])
            if self.clock.now() < history_instant(batch["due_at"]):
                return {"status": "buffering", "run_id": None}
            return self._flush(batch)

    def _flush(self, batch: dict[str, Any]) -> dict[str, Any]:
        owner = batch["owner_user_id"]
        if batch["batch_state"] == "queued":
            run = self.repo.fetch_run(owner, batch["run_id"])
            return {"status": run["status"], "run_id": run["id"]}
        first = self.repo.get(owner, "request", batch["inbound_ids"][0])
        run = self.ingress.queue(
            owner=owner,
            subject=batch["subject_id"],
            thread_id=batch["thread_id"],
            source_ids=batch["source_ids"],
            request_id=first["business_id"],
            conversation_id="feishu:p2p:" + batch["chat_id"],
            mode="chat",
            depth="standard",
        )
        for ident in batch["inbound_ids"]:
            item = self.repo.get(owner, "request", ident)
            if (item.get("batch_id"), item["subject_id"], item.get("target"), item.get("chat_id")) != (
                batch["id"],
                batch["subject_id"],
                batch["target"],
                batch["chat_id"],
            ):
                raise ScopeError("飞书合并来源身份不一致")
            self.repo.update(
                owner,
                "request",
                ident,
                dict(run_id=run["id"], business_id=first["business_id"]),
                expected_revision=item["revision"],
            )
        self.repo.update(
            owner,
            "request",
            batch["id"],
            dict(batch_state="queued", run_id=run["id"]),
            expected_revision=batch["revision"],
        )
        return {"status": run["status"], "run_id": run["id"]}

    def flush_due(self) -> dict[str, int]:
        with self.repo.connection() as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT owner,id FROM {} WHERE kind='request' AND status='active' "
                    "AND data->>'ingress'='feishu_batch' AND data->>'batch_state'='buffering' "
                    "AND (data->>'due_at')::timestamptz<=%s ORDER BY created_at,id LIMIT 1000"
                ).format(self.repo.table("core_entities")),
                (self.clock.now(),),
            ).fetchall()
        counts = {"queued": 0, "failed": 0}
        for row in rows:
            try:
                with self.repo.transaction(row["owner"]):
                    self._flush(self.repo.get(row["owner"], "request", row["id"]))
                    counts["queued"] += 1
            except (EvidenceError, ScopeError):
                counts["failed"] += 1
        for owner in {row["owner"] for row in rows}:
            ThreadInbox(self.repo).recover(owner)
        return counts

"""Verify Hermes original messages, then pass their authoritative IDs to Core.

The Hermes database is opened read-only. A nickname, transcript supplied by a
model, or a guessed private chat never establishes identity.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hermes.state_store import EvidenceError, ScopeError, StateStore


class HermesChannelAdapter:
    def __init__(self, base: str | Path, *, service=None, hermes_db: str | Path | None = None):
        self.base = Path(base)
        self.state = StateStore(self.base)
        self.hermes_db = Path(hermes_db or os.environ.get("HERMES_DB", "/root/.hermes/state.db"))
        self._service = service

    @property
    def service(self):
        if self._service is None:
            from mingjing_core.application.consultation import ConsultationService
            self._service = ConsultationService.from_base(self.base)
        return self._service

    def identity(self, channel: str, external_id: str) -> dict[str, Any]:
        if not channel or not external_id:
            raise ScopeError("需要显式绑定的 channel 与 external_id，不能猜测身份")
        if channel in ("web", "report", "cron"):
            raise ScopeError("此适配器只接收 Hermes 渠道原始用户消息")
        return self.state.resolve_channel(channel, str(external_id))

    def original_rows(self, channel: str, external_id: str, *, binding_kind: str = "user", message_id: str | None = None):
        """Read only active user messages in a verified private conversation."""
        self.identity(channel, external_id)
        if binding_kind not in ("user", "chat"):
            raise ValueError("绑定方式仅支持 user 或 chat")
        if not self.hermes_db.is_file():
            raise EvidenceError("Hermes 原始消息库不可用")
        db = sqlite3.connect(self.hermes_db.resolve().as_uri() + "?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            sessions = {row[1] for row in db.execute("PRAGMA table_info(sessions)")}
            messages = {row[1] for row in db.execute("PRAGMA table_info(messages)")}
            if not {"id", "source", "user_id", "chat_id", "chat_type"} <= sessions or not {
                "id", "session_id", "role", "content", "timestamp", "active"
            } <= messages:
                raise EvidenceError("原始消息缺少身份或有效状态字段，拒绝猜测归属")
            field = "user_id" if binding_kind == "user" else "chat_id"
            if binding_kind == "chat":
                authors = {str(row[0] or "").strip() for row in db.execute(
                    "SELECT DISTINCT user_id FROM sessions WHERE source=? AND chat_type='dm' AND chat_id=?",
                    (channel, str(external_id)),
                )}
                if len(authors) != 1 or "" in authors:
                    raise ScopeError("私聊标识不能唯一确认原始作者，须先修复绑定")
            query = (
                "SELECT m.id,m.content,m.timestamp,s.id AS session_id,s.user_id,s.chat_id "
                "FROM messages m JOIN sessions s ON s.id=m.session_id "
                "WHERE s.source=? AND s.chat_type='dm' AND s." + field + "=? "
                "AND m.role='user' AND m.active=1"
            )
            args: list[Any] = [channel, str(external_id)]
            if message_id is not None:
                query += " AND m.id=?"
                args.append(str(message_id))
            rows = [dict(row) for row in db.execute(query + " ORDER BY m.timestamp,m.id", args)]
            if any(not str(row["user_id"] or "").strip() for row in rows):
                raise EvidenceError("原始消息缺少用户标识")
            if len({str(row["id"]) for row in rows}) != len(rows):
                raise EvidenceError("原始消息标识存在冲突，不能确认唯一来源")
            return rows
        finally:
            db.close()

    def _revoked(self, owner: str, channel: str, message_id: str) -> bool:
        with self.state.db() as db:
            return self.state._suppressed(db, owner, channel, str(message_id) + ":user")

    def _register(self, binding: dict, channel: str, external_id: str, row: dict):
        if self._revoked(binding["owner"], channel, row["id"]):
            raise EvidenceError("这条原话已停止使用或删除，不能重新导入")
        content = row["content"]
        if not isinstance(content, str) or not content.strip():
            raise EvidenceError("原始用户消息为空或格式不可用")
        stamp = row["timestamp"]
        if isinstance(stamp, (int, float)):
            stamp = datetime.fromtimestamp(stamp, timezone.utc)
        original = self.state.import_message(
            binding["owner"], channel, str(row["id"]) + ":user", "user", content, stamp,
            subject=binding["subject"], channel=channel, external_id=external_id,
            conversation_id=channel + ":" + str(row["session_id"]),
        )
        # A concurrent withdrawal between the pre-check and insert must not
        # create an apparently usable current source.
        return self.state.get_message(binding["owner"], original["id"])

    def sync(self, channel: str, external_id: str, *, binding_kind: str = "user") -> dict[str, int]:
        binding = self.identity(channel, external_id)
        imported = skipped = 0
        for row in self.original_rows(channel, external_id, binding_kind=binding_kind):
            if self._revoked(binding["owner"], channel, row["id"]) or not isinstance(row["content"], str) or not row["content"].strip():
                skipped += 1
                continue
            try:
                self._register(binding, channel, external_id, row)
                imported += 1
            except EvidenceError:
                # Concurrent withdrawal is safe to skip, other source errors
                # are real integrity failures and must not be hidden.
                if not self._revoked(binding["owner"], channel, row["id"]):
                    raise
                skipped += 1
        return {"imported": imported, "skipped": skipped}

    async def consult(self, *, channel: str, external_id: str, message_id: str,
                      request_id: str | None = None, binding_kind: str = "user",
                      conversation_id: str | None = None, case_ids=None, draw=None,
                      depth: str = "standard", emit=None):
        binding = self.identity(channel, external_id)
        rows = self.original_rows(channel, external_id, binding_kind=binding_kind, message_id=message_id)
        if len(rows) != 1:
            raise EvidenceError("未找到属于当前绑定身份的有效用户原话")
        # Verify the current source before synchronizing older messages, so a
        # forged/withdrawn message cannot initiate any consultation.
        source = self._register(binding, channel, external_id, rows[0])
        self.sync(channel, external_id, binding_kind=binding_kind)
        self.state.get_message(binding["owner"], source["id"])
        result = await self.service.consult(
            owner=binding["owner"], subject=binding["subject"], message=source["content"],
            conversation_id=conversation_id or channel + ":" + str(rows[0]["session_id"]),
            case_ids=case_ids, draw=draw, request_id=request_id or channel + ":" + str(message_id),
            source_message_id=source["id"], depth=depth, emit=emit,
        )
        validated_payload(result)
        return result


def validated_payload(result: dict) -> dict:
    """Rendering cannot grant validity to an unverified or legacy result."""
    if not isinstance(result, dict) or result.get("validation", {}).get("core_version") != "3.0":
        raise EvidenceError("渠道只接受明镜 Core 已校验的最终 payload")
    meta = result.get("meta", {})
    if not meta.get("core_run") or not meta.get("reading_id") or not meta.get("episode_id"):
        raise EvidenceError("结果缺少权威执行或解读版本标识")
    if not isinstance(result.get("answer"), str) or not result["answer"].strip():
        raise EvidenceError("已校验结果没有可投递正文")
    return result


def render_channel(result: dict) -> str:
    """Return the exact validated body; never invoke another model."""
    return validated_payload(result)["answer"]

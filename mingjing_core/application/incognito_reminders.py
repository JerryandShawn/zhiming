"""Z4 one-time approval; only approved reminder text/time escape the private thread."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import sql

from mingjing_core.application.agent_tools_followups import due_instant, reminder_intent
from mingjing_core.application.agent_tools_policy import CREDENTIAL
from mingjing_core.application.memory import SECRET
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.memory.private import is_private
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.timestamps import history_instant

CONFIRM_QUESTION = "这条提醒要保存下来才能按时提醒你，只保存提醒内容和时间，不保存这段对话，可以吗？"
ACCEPT = frozenset({"同意", "可以", "确认", "是", "好", "yes"})
DECLINE = frozenset({"不同意", "不可以", "取消", "不要", "不保存", "不", "no"})


class IncognitoReminderService:
    def __init__(self, repo: PostgresRepository, *, clock: Clock | None = None) -> None:
        self.repo, self.clock = repo, clock or get_clock()
        self.threads = ThreadService(repo, clock=self.clock)

    @contextmanager
    def _context(self, owner: str, supplied: Mapping[str, Any]) -> Iterator[tuple[dict, dict, dict]]:
        original = self.repo.fetch_run(owner, supplied["id"])
        ident = original["thread_id"]
        if not isinstance(ident, str) or not ident.startswith("incognito:"):
            raise ScopeError("这项确认只适用于当前无痕线程")
        with self.repo.transaction(owner) as connection:
            self.threads._lock(connection, owner, ident)
            row = self.repo._leased(connection, owner, original["id"], supplied["lease_token"])
            if row["runtime"] != "v4" or row["retry_epoch"] != supplied["retry_epoch"] or row["cancel_requested_at"]:
                raise LeaseConflict("无痕提醒确认的运行已失效")
            if row["deadline_at"] is not None and row["deadline_at"] <= self.clock.now():
                raise LeaseConflict("无痕提醒确认已超时")
            thread = self.threads.get(owner, ident, subject=row["subject"])
            run = self.repo._run(row)
            source = self.threads.memory.get_source(owner, run["request"]["source_message_id"], for_context=True)
            if (
                source["subject_id"] != run["subject"]
                or source.get("thread_id") != ident
                or source["status"] != "active"
                or source.get("role") != "user"
                or not is_private(source)
                or source.get("policy", {}).get("origin") != "current_user"
                or source.get("policy", {}).get("run_context") is not True
                or source["content"] != run["request"].get("message")
                or self.repo.is_revoked(owner, "message", source["id"])
            ):
                raise EvidenceError("无痕提醒只接受本轮有效用户原话")
            latest = self.threads.history(owner, ident, subject=row["subject"], limit=1)
            if not latest or latest[-1]["id"] != source["id"]:
                raise EvidenceError("无痕提醒确认必须来自当前最新消息")
            yield run, thread, source

    def begin(self, owner: str, run: Mapping[str, Any], *, text: str, due_at: str) -> dict[str, Any]:
        with self._context(owner, run) as (current, thread, source):
            if not isinstance(text, str) or not 1 <= len(text) <= 500 or text not in source["content"]:
                raise EvidenceError("提醒内容必须逐字来自当前原话")
            if SECRET.search(text) or CREDENTIAL.search(text) or reminder_intent(source["content"]) != "confirmed":
                raise EvidenceError("提醒需要明确请求且不能包含凭据")
            due = due_instant(due_at)
            settings = self.repo.assert_scope(owner, current["subject"])["settings"]
            local = due.astimezone(ZoneInfo(settings.get("timezone", "Asia/Shanghai")))
            # Until the shared U4 parser is wired, accept only user-confirmed
            # absolute dates and minute precision; never guess relative dates.
            if (
                due <= self.clock.now()
                or local.date().isoformat() not in source["content"]
                or local.strftime("%H:%M") not in source["content"]
            ):
                raise EvidenceError("提醒时间需要原话里的绝对日期和时刻")
            pending = thread.get("reminder_confirmation")
            if pending and (pending["state"] == "pending" or pending["source_id"] == source["id"]):
                return {"status": "already_asked", "asked": None, "request_id": pending["request_id"]}
            request_id = "incognito-reminder-" + fingerprint([owner, source["id"], text, due.isoformat()])[:32]
            pending = dict(
                request_id=request_id,
                text=text,
                due_at=due.isoformat(),
                state="pending",
                source_id=source["id"],
                source_revision=source["revision"],
                asked_at=self.clock.now().isoformat(),
            )
            self.repo.update(
                owner, "thread", thread["id"], {"reminder_confirmation": pending}, expected_revision=thread["revision"]
            )
            return {"status": "confirmation_required", "request_id": request_id, "asked": self.question(request_id)}

    @staticmethod
    def question(request_id: str) -> dict[str, Any]:
        return dict(
            ask_id=request_id,
            question=CONFIRM_QUESTION,
            options=[{"id": "accept", "label": "可以"}, {"id": "decline", "label": "不保存"}],
            allow_free_text=True,
            multi=False,
            why="提醒需要单独保存内容与时间才能触发",
        )

    def confirm(self, owner: str, run: Mapping[str, Any], *, request_id: str) -> dict[str, Any]:
        with self._context(owner, run) as (current, thread, source):
            pending = thread.get("reminder_confirmation")
            if not isinstance(pending, dict) or pending.get("request_id") != request_id:
                raise EvidenceError("无痕提醒确认已失效")
            if pending["state"] != "pending":
                return {"write_status": pending["state"], "id": pending.get("reminder_id")}
            if source["id"] == pending["source_id"]:
                raise EvidenceError("必须由用户在确认问题之后另行回答")
            original = self.threads.memory.get_source(owner, pending["source_id"], for_context=True)
            if original["status"] != "active" or original["revision"] != pending["source_revision"]:
                raise EvidenceError("提醒原始请求已改变或撤销")
            if pending["text"] not in original["content"]:
                raise EvidenceError("提醒原始内容已撤销")
            answer = source["content"].strip().rstrip("。.!！").casefold()
            if answer not in ACCEPT | DECLINE:
                return {"write_status": "pending_confirm", "id": None}
            state, ident = "rejected", None
            if answer in ACCEPT:
                row = self._save(owner, current["subject"], pending)
                state, ident = "saved", row["id"]
            self.repo.update(
                owner,
                "thread",
                thread["id"],
                {"reminder_confirmation": dict(pending, state=state, reminder_id=ident)},
                expected_revision=thread["revision"],
            )
            return {"write_status": state, "id": ident, "kind": "reminder"}

    def _save(self, owner: str, subject: str, pending: dict[str, Any]) -> dict[str, Any]:
        due = due_instant(pending["due_at"])
        if due <= self.clock.now():
            raise EvidenceError("提醒时间已过，请重新确认")
        ident = "reminder_" + fingerprint([owner, pending["request_id"]])[:32]
        return self.repo.put(
            owner,
            "reminder",
            ident,
            dict(
                text=pending["text"],
                topic=pending["text"],
                due_at=due.isoformat(),
                due_ms=int(due.timestamp() * 1000),
                source="incognito_explicit",
                explicit=True,
                channel="web",
                status="active",
            ),
            subject=subject,
            expected_revision=0,
            operation_id="incognito-reminder:" + ident,
        )

    def delivered(self, owner: str, ident: str, *, outbox_id: str, expected_revision: int) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            row = self.repo.get(owner, "reminder", ident)
            if row.get("source") != "incognito_explicit":
                raise EvidenceError("这项保留规则只适用于已确认的无痕提醒")
            sent = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(
                    self.repo.table("delivery_outbox")
                ),
                (owner, outbox_id),
            ).fetchone()
            if (
                not sent
                or sent["business_id"] != "reminder:" + ident
                or sent["status"] != "sent"
                or not sent["receipt"]
                or sent["subject"] != row["subject_id"]
            ):
                raise EvidenceError("提醒尚无真实已发送收据")
            at = history_instant(sent["updated_at"])
            if at is None or at > self.clock.now():
                raise EvidenceError("提醒收据时间无效")
            if row.get("delivered_at"):
                return row
            return self.repo.update(
                owner,
                "reminder",
                ident,
                {"delivered_at": at.isoformat(), "delete_after": (at + timedelta(days=7)).isoformat()},
                expected_revision=expected_revision,
            )

    def cleanup_delivered(self, owner: str) -> int:
        retired = 0
        for row in self.repo.list(owner, "reminder"):
            expires = history_instant(row.get("delete_after"))
            if row.get("source") == "incognito_explicit" and expires is not None and expires <= self.clock.now():
                with self.repo.transaction(owner) as connection:
                    self.repo.delete(owner, "reminder", row["id"], expected_revision=row["revision"])
                    connection.execute(
                        sql.SQL(
                            "UPDATE {} SET payload='{{}}',dependencies='{{}}' WHERE owner=%s AND business_id=%s"
                        ).format(self.repo.table("delivery_outbox")),
                        (owner, "reminder:" + row["id"]),
                    )
                retired += 1
        return retired

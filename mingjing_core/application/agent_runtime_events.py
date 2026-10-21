"""Validated public events commit before a caller's delivery callback runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from psycopg import sql

from mingjing_core.agent.events import validate_event
from mingjing_core.agent.journal import Journal
from mingjing_core.application.agent_thread_scope import assert_thread, thread_id
from mingjing_core.application.public_tool_ids import public_call_id
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.run_event_log import append_event


class RuntimeEvents:
    def __init__(self, repo: PostgresRepository, run: dict[str, Any], callback: Callable[[dict], None] | None) -> None:
        self.repo, self.run, self.callback = repo, run, callback

    def _existing(self, connection: Any, kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        rows = connection.execute(
            sql.SQL("SELECT seq,payload FROM {} WHERE owner=%s AND run_id=%s AND kind=%s ORDER BY seq").format(
                self.repo.table("core_run_events")
            ),
            (self.run["owner"], self.run["id"], kind),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise EvidenceError("已提交终止事件重复，不能改写")
        row = rows[0]
        value = validate_event(kind, row["payload"])
        body = {key: child for key, child in value.items() if key not in {"v", "run_id", "seq", "ts"}}
        if body != payload or value["run_id"] != self.run["id"] or value["seq"] != row["seq"]:
            raise EvidenceError("已有终止事件与真实提交不符，不能覆盖")
        return {"type": kind, "data": value}

    def send(self, kind: str, payload: dict[str, Any], *, operation_key: str | None = None) -> None:
        if kind in {"tool_call", "tool_result"}:
            payload = dict(payload, call_id=public_call_id(self.run, payload.get("call_id")))
        owner, ident = self.run["owner"], self.run["id"]
        with self.repo.transaction(owner) as connection:
            if kind in {"final", "ask_user", "present_options"}:
                row = connection.execute(
                    sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(
                        self.repo.table("core_runs")
                    ),
                    (owner, ident),
                ).fetchone()
                field = "asked" if kind == "ask_user" else "options"
                expected = (
                    row["result"] if row and kind == "final" else (row["result"] or {}).get(field) if row else None
                )
                actual = payload.get("envelope") if kind == "final" else payload
                if not row or row["status"] != "succeeded" or expected != actual:
                    raise EvidenceError("最终事件缺少已提交的真实信封")
            else:
                row = Journal(self.repo, owner)._leased(connection, self.run)
            if row["subject"] != self.run["subject"] or thread_id(row) != thread_id(self.run):
                raise EvidenceError("事件人物或线程与当前运行不符")
            if row["retry_epoch"] != self.run["retry_epoch"]:
                raise EvidenceError("事件不属于当前运行批次")
            assert_thread(self.repo, row)
            event = (
                self._existing(connection, kind, payload) if kind in {"final", "ask_user", "present_options"} else None
            )
            key = "started:v1" if kind == "started" and operation_key is None else operation_key
            event = event or append_event(self.repo, connection, self.run, kind, payload, operation_key=key)
        if self.callback:
            try:
                self.callback(event)
            except Exception:
                # A disconnected UI cannot roll back an already durable reply.
                return

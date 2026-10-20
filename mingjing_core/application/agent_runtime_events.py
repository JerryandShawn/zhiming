"""Validated public events commit before a caller's delivery callback runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.events import make_event, validate_event
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository


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

    def _append(self, connection: Any, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        owner, ident = self.run["owner"], self.run["id"]
        seq = connection.execute(
            sql.SQL("SELECT coalesce(max(seq),0)+1 AS seq FROM {} WHERE owner=%s AND run_id=%s").format(
                self.repo.table("core_run_events")
            ),
            (owner, ident),
        ).fetchone()["seq"]
        event = make_event(kind, ident, seq, payload)
        connection.execute(
            sql.SQL("INSERT INTO {}(owner,run_id,seq,kind,payload) VALUES(%s,%s,%s,%s,%s)").format(
                self.repo.table("core_run_events")
            ),
            (owner, ident, seq, kind, Jsonb(event["data"])),
        )
        return event

    def send(self, kind: str, payload: dict[str, Any]) -> None:
        owner, ident = self.run["owner"], self.run["id"]
        with self.repo.transaction(owner) as connection:
            if kind in {"final", "ask_user"}:
                row = connection.execute(
                    sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(
                        self.repo.table("core_runs")
                    ),
                    (owner, ident),
                ).fetchone()
                expected = (
                    row["result"] if row and kind == "final" else (row["result"] or {}).get("asked") if row else None
                )
                actual = payload.get("envelope") if kind == "final" else payload
                if not row or row["status"] != "succeeded" or expected != actual:
                    raise EvidenceError("最终事件缺少已提交的真实信封")
            else:
                row = self.repo._leased(connection, owner, ident, self.run["lease_token"])
                if row["retry_epoch"] != self.run["retry_epoch"]:
                    raise EvidenceError("事件不属于当前运行批次")
            event = self._existing(connection, kind, payload) if kind in {"final", "ask_user"} else None
            event = event or self._append(connection, kind, payload)
        if self.callback:
            try:
                self.callback(event)
            except Exception:
                # A disconnected UI cannot roll back an already durable reply.
                return

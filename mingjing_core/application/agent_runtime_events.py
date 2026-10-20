"""Validated public events commit before a caller's delivery callback runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.events import make_event
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import PostgresRepository


class RuntimeEvents:
    def __init__(self, repo: PostgresRepository, run: dict[str, Any], callback: Callable[[dict], None] | None) -> None:
        self.repo, self.run, self.callback = repo, run, callback

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
        if self.callback:
            try:
                self.callback(event)
            except Exception:
                # A disconnected UI cannot roll back an already durable reply.
                return

"""Owner-scoped frozen event replay, including recovery after the final event gap."""

from __future__ import annotations

from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.events import validate_event
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.agent_thread_scope import assert_thread
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.repositories.postgres import fingerprint
from mingjing_core.repositories.run_event_log import append_event

TERMINAL = {"succeeded", "failed", "stale", "cancelled", "revoked"}
ERRORS = {
    "failed": ("RUN_FAILED", "本轮尚未完成，请恢复原请求", True),
    "stale": ("RUN_STALE", "本轮采用的资料已改变，请恢复原请求", True),
    "cancelled": ("RUN_CANCELLED", "本轮已停止", False),
    "revoked": ("SOURCE_REVOKED", "本轮采用的资料已撤销", False),
}


class RunEventReader:
    def __init__(self, repo: Any, owner: str, ident: str) -> None:
        self.repo, self.owner, self.ident = repo, owner, ident
        self.authority()

    def authority(self) -> dict[str, Any]:
        run = self.repo.fetch_run(self.owner, self.ident)
        self.repo.assert_scope(self.owner, run["subject"])
        if run["runtime"] != "v4":
            raise EvidenceError("此事件入口仅支持 v4 运行")
        if run["status"] not in {"revoked", "cancelled"}:
            assert_thread(self.repo, run)
        return run

    def validate_cursor(self, after: int) -> None:
        if type(after) is not int or not 0 <= after < 2**63:
            raise EvidenceError("事件游标无效")
        self.authority()
        if after == 0:
            return
        with self.repo.transaction(self.owner) as connection:
            original = connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
                    self.repo.table("core_run_events")
                ),
                (self.owner, self.ident, after),
            ).fetchone()
        if original is None:
            raise EvidenceError("事件游标不可用，请重新读取运行状态")

    def ensure_terminal(self) -> dict[str, Any]:
        with self.repo.transaction(self.owner) as connection:
            raw = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(self.repo.table("core_runs")),
                (self.owner, self.ident),
            ).fetchone()
            run = self.repo._run(raw)
            if run["status"] not in TERMINAL:
                return run
            if run["status"] == "succeeded":
                events = RuntimeEvents(self.repo, run, None)
                if run["result"].get("asked"):
                    events.send("ask_user", run["result"]["asked"])
                if run["result"].get("options"):
                    events.send("present_options", run["result"]["options"])
                events.send("final", {"message_id": run["result"]["message_id"], "envelope": run["result"]})
                return run
            self._error(connection, run)
            return run

    def _error(self, connection: Any, run: dict[str, Any]) -> None:
        code, message, retryable = ERRORS[run["status"]]
        payload = {"code": code, "message": message, "retryable": retryable}
        tag = {"attempts": run["attempts"], "epoch": run["retry_epoch"], "status": run["status"]}
        previous = run["usage"].get("event_terminal_error", {})
        if all(previous.get(key) == value for key, value in tag.items()):
            old = connection.execute(
                sql.SQL("SELECT payload FROM {} WHERE owner=%s AND run_id=%s AND seq=%s").format(
                    self.repo.table("core_run_events")
                ),
                (self.owner, self.ident, previous.get("seq")),
            ).fetchone()
            value = validate_event("error", old["payload"]) if old else {}
            if any(value.get(key) != item for key, item in payload.items()) or value.get("run_id") != self.ident:
                raise EvidenceError("已有停止事件损坏，不能覆盖")
            return
        event = append_event(
            self.repo, connection, run, "error", payload, operation_key="terminal-error:v1:" + fingerprint(tag)
        )
        seq = event["data"]["seq"]
        usage = dict(run["usage"], event_terminal_error=dict(tag, seq=seq))
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
            (Jsonb(usage), self.owner, self.ident),
        )

    def page(self, after: int) -> tuple[list[dict[str, Any]], int, bool]:
        self.authority()
        run = self.ensure_terminal()
        with self.repo.transaction(self.owner) as connection:
            rows = connection.execute(
                sql.SQL(
                    "SELECT seq,kind,payload FROM {} WHERE owner=%s AND run_id=%s AND seq>%s ORDER BY seq LIMIT 256"
                ).format(self.repo.table("core_run_events")),
                (self.owner, self.ident, after),
            ).fetchall()
        events = []
        for row in rows:
            after = row["seq"]
            # Withdrawal intentionally clears old payloads; never reconstruct them.
            if not row["payload"]:
                continue
            events.append({"type": row["kind"], "data": validate_event(row["kind"], row["payload"])})
        return events, after, run["status"] in TERMINAL and len(rows) < 256

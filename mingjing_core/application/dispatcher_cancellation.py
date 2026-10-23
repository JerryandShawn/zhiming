"""Owner-bound stop requests and provenance-checked interrupted partial replies."""

from __future__ import annotations

from typing import Any

from psycopg import sql

from mingjing_core.application.dispatcher_notifications import RunSignals
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.dispatch_hooks import notify_run
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import get_clock


class DispatcherCancellation:
    def __init__(self, repo: PostgresRepository, signals: RunSignals | None = None) -> None:
        self.repo, self.signals = repo, signals

    def request(self, owner: str, ident: str) -> dict[str, Any]:
        with self.repo.transaction(owner) as connection:
            row = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE owner=%s AND id=%s FOR UPDATE").format(self.repo.table("core_runs")),
                (owner, ident),
            ).fetchone()
            if not row or row["runtime"] != "v4":
                raise ScopeError("停止请求不属于当前所有者的 v4 运行")
            if row["status"] in {"queued", "running"}:
                connection.execute(
                    sql.SQL(
                        "UPDATE {} SET cancel_requested_at=coalesce(cancel_requested_at,%s),"
                        "status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END,updated_at=now() "
                        "WHERE owner=%s AND id=%s"
                    ).format(self.repo.table("core_runs")),
                    (get_clock().now(), owner, ident),
                )
                notify_run(connection, self.repo.schema, ident, cancel=True)
            result = self.repo.fetch_run(owner, ident)
        if self.signals and result["cancel_requested_at"]:
            self.signals.cancel(ident)
        return result

    def _partial(self, connection: Any, run: dict[str, Any]) -> str:
        rows = connection.execute(
            sql.SQL(
                "SELECT kind,payload FROM {} WHERE owner=%s AND run_id=%s "
                "AND kind IN ('text_delta','text_reset') ORDER BY seq"
            ).format(self.repo.table("core_run_events")),
            (run["owner"], run["id"]),
        ).fetchall()
        text = ""
        for row in rows:
            fragment = row["payload"].get("text", "")
            if isinstance(fragment, str):
                text = fragment if row["kind"] == "text_reset" else text + fragment
            if len(text) > 200_000:
                raise EvidenceError("中断正文超过保留上限")
        return text

    def _save(self, run: dict[str, Any], text: str) -> str:
        source = MemoryService(self.repo).get_source(run["owner"], run["request"].get("source_message_id"))
        if (
            source["status"] != "active"
            or source["subject_id"] != run["subject"]
            or source.get("role") != "user"
            or source.get("policy", {}).get("origin") != "current_user"
            or source.get("policy", {}).get("run_context") is not True
            or source.get("content") != run["request"].get("message")
            or run["state_version"].get("message:" + source["id"]) != source["revision"]
            or not self.repo.verify_versions(run["owner"], run["state_version"])
        ):
            raise EvidenceError("中断正文的采用来源已经失效")
        thread = run["thread_id"] or "life:" + run["subject"]
        private = thread.startswith("incognito:")
        now = get_clock().now()
        ident = "msg_" + fingerprint([run["owner"], run["id"], "interrupted"])[:32]
        self.repo.put(
            run["owner"],
            "message",
            ident,
            {
                "status": "interrupted",
                "content": text,
                "role": "assistant",
                "thread_id": thread,
                "incognito": private,
                "run_id": run["id"],
                "at": now.isoformat(),
                "at_ms": int(now.timestamp() * 1000),
                "channel": source["channel"],
                "source_ids": [key[8:] for key in run["state_version"] if key.startswith("message:")],
                "used_fact_ids": [key[5:] for key in run["state_version"] if key.startswith("fact:")],
                "policy": {"origin": "system", "run_context": False, "persist_allowed": not private},
            },
            subject=run["subject"],
            expected_revision=0,
            operation_id="interrupted:" + run["id"],
        )
        return ident

    def finish(self, run: dict[str, Any]) -> dict[str, Any]:
        with self.repo.transaction(run["owner"]) as connection:
            previous = self.repo.fetch_run(run["owner"], run["id"])
            if previous["status"] == "cancelled" and previous["retry_epoch"] == run["retry_epoch"]:
                return previous
            current = self.repo._run(self.repo._leased(connection, run["owner"], run["id"], run["lease_token"]))
            if current["runtime"] != "v4" or current["retry_epoch"] != run["retry_epoch"]:
                raise LeaseConflict("中断批次或运行版本不符")
            if not current["cancel_requested_at"]:
                raise EvidenceError("没有用户停止标记，不能保存中断正文")
            try:
                text = self._partial(connection, current)
                if text.strip():
                    self._save(current, text)
            except EvidenceError:
                # An unsafe partial is discarded; it must not delay the stop.
                text = ""
            return self.repo.fail_run(run["owner"], run["id"], "本轮已停止", run["lease_token"], status="cancelled")

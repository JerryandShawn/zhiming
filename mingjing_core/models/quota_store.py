"""Short, account-serialized PostgreSQL operations for the central quota guard."""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .quota_types import (
    STOP_KINDS,
    GuardConfigurationError,
    GuardRejected,
    QuotaPolicy,
    identifier,
)


class QuotaStore:
    def __init__(self, dsn: str, schema: str, account_id: str, ledger_identity: str) -> None:
        if not dsn or not schema or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", schema) is None:
            raise GuardConfigurationError("必须明确配置中央账本连接和schema")
        try:
            identity = str(uuid.UUID(ledger_identity))
        except (ValueError, TypeError, AttributeError):
            raise GuardConfigurationError("中央账本身份必须是固定UUID") from None
        self.dsn, self.schema = dsn, schema
        self.account_id, self.identity = identifier(account_id), identity

    def connect(self) -> psycopg.Connection[Any]:
        failed = False
        try:
            connection = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row, connect_timeout=5)
        except psycopg.Error:
            failed = True
        if failed:
            raise GuardRejected("ledger_unavailable")
        return connection

    def table(self, name: str) -> sql.Identifier:
        return sql.Identifier(self.schema, name)

    def location(self, connection: psycopg.Connection[Any]) -> str:
        row = connection.execute(
            "SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port"
        ).fetchone()
        if row["host"] is None:
            raise GuardConfigurationError("中央账本需要明确的TCP数据库地址")
        value = f"{row['db']}:{row['host']}:{row['port']}:{self.schema}"
        return hashlib.sha256(value.encode()).hexdigest()

    def verify(self, connection: psycopg.Connection[Any], *, lock: bool = False) -> dict[str, Any]:
        present = connection.execute(
            "SELECT to_regclass(%s) AS name",
            (f'"{self.schema}"."core_model_accounts"',),
        ).fetchone()
        if present["name"] is None:
            raise GuardConfigurationError("中央账号账本尚未部署")
        query = sql.SQL("SELECT * FROM {} WHERE account_id=%s").format(self.table("core_model_accounts"))
        if lock:
            query += sql.SQL(" FOR UPDATE")
        row = connection.execute(query, (self.account_id,)).fetchone()
        if (
            row is None
            or str(row["ledger_identity"]) != self.identity
            or row["location_id"] != self.location(connection)
        ):
            raise GuardConfigurationError("中央账号账本未部署或身份不符")
        return row

    def provision(self, connection: psycopg.Connection[Any]) -> None:
        """Migration/admin-only bootstrap; runtime construction never creates an account."""
        location = self.location(connection)
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(account_id,ledger_identity,location_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING"
            ).format(self.table("core_model_accounts")),
            (self.account_id, self.identity, location),
        )
        self.verify(connection)

    def locked(
        self,
        connection: psycopg.Connection[Any],
        now: datetime,
        *,
        stopped: bool = False,
    ) -> dict[str, Any]:
        row = self.verify(connection, lock=True)
        if row["last_clock_at"] is not None and now < row["last_clock_at"]:
            raise GuardRejected("clock_rollback")
        if not stopped and row["stop_kind"]:
            raise GuardRejected(row["stop_kind"], row["resume_at"])
        connection.execute(
            sql.SQL("UPDATE {} SET last_clock_at=%s WHERE account_id=%s").format(self.table("core_model_accounts")),
            (now, self.account_id),
        )
        return row

    def counts(self, connection: psycopg.Connection[Any], now: datetime, policy: QuotaPolicy) -> dict[str, Any]:
        return connection.execute(
            sql.SQL(
                "SELECT count(*) AS total,min(at) AS oldest,"
                "count(*) FILTER(WHERE bucket='interactive') AS interactive,"
                "count(*) FILTER(WHERE bucket='critic') AS critic,"
                "count(*) FILTER(WHERE bucket='background') AS background,"
                "count(*) FILTER(WHERE lane IN ('eval','probe')) AS evaluation,"
                "count(*) FILTER(WHERE finished_at IS NULL) AS unfinished "
                "FROM {} WHERE account_id=%s AND at>%s AND at<=%s"
            ).format(self.table("core_model_usage")),
            (self.account_id, now - policy.window, now),
        ).fetchone()

    def finalizing(self, connection: psycopg.Connection[Any], now: datetime) -> datetime:
        # A local clock adjustment must not discard an already observed terminal stop.
        row = self.verify(connection, lock=True)
        now = max(now, row["last_clock_at"] or now)
        connection.execute(
            sql.SQL("UPDATE {} SET last_clock_at=%s WHERE account_id=%s").format(self.table("core_model_accounts")),
            (now, self.account_id),
        )
        return now

    def control_action(
        self, connection: psycopg.Connection[Any], authorization: str, kind: str, batch: str | None, now: datetime
    ) -> bool:
        """Append-only operation identity prevents a stale human action affecting new work."""
        old = connection.execute(
            sql.SQL("SELECT kind,batch_id FROM {} WHERE account_id=%s AND authorization_id=%s").format(
                self.table("core_model_authorizations")
            ),
            (self.account_id, authorization),
        ).fetchone()
        if old:
            if old["kind"] != kind or old["batch_id"] != batch:
                raise GuardRejected("manual_start_required")
            return False
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(account_id,authorization_id,batch_id,kind,created_at,expires_at) "
                "VALUES(%s,%s,%s,%s,%s,%s)"
            ).format(self.table("core_model_authorizations")),
            (self.account_id, authorization, batch, kind, now, now),
        )
        return True

    def check_batch(self, connection: psycopg.Connection[Any], data: dict[str, Any], now: datetime) -> None:
        if data["lane"] not in {"eval", "probe"}:
            if any(data.get(key) is not None for key in ("batch_id", "authorization_id", "scenario_id")):
                raise GuardConfigurationError("交互或后台调用不能伪装评测批次")
            return
        row = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE account_id=%s AND batch_id=%s").format(self.table("core_model_batches")),
            (self.account_id, data.get("batch_id")),
        ).fetchone()
        if row is None or row["status"] != "active" or row["authorization_id"] != data.get("authorization_id"):
            raise GuardRejected("manual_start_required")
        if now >= row["expires_at"]:
            raise GuardRejected("authorization_expired")
        if data.get("scenario_id") not in row["scenario_ids"]:
            raise GuardRejected("batch_conflict")

    def reserve(
        self,
        connection: psycopg.Connection[Any],
        data: dict[str, Any],
        now: datetime,
        policy: QuotaPolicy,
    ) -> None:
        rejected = None
        with connection.transaction():
            self.locked(connection, now)
            old = connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE account_id=%s AND attempt_id=%s").format(
                    self.table("core_model_usage")
                ),
                (self.account_id, data["attempt_id"]),
            ).fetchone()
            if old:
                raise GuardRejected("attempt_replayed")
            counts = self.counts(connection, now, policy)
            if counts["total"] >= policy.max_calls:
                resume = counts["oldest"] + policy.window
                self.stop(connection, "member_window_limit", now, resume_at=resume)
                rejected = GuardRejected("member_window_limit", resume)
            elif data["bucket"] != "interactive" and counts[data["bucket"]] >= policy.limit(data["bucket"]):
                raise GuardRejected("share_limit")
            elif data["lane"] in {"eval", "probe"} and counts["evaluation"] >= policy.eval_max_calls:
                self.stop(connection, "member_window_limit", now)
                rejected = GuardRejected("member_window_limit", now + policy.window)
            if rejected is None:
                self.check_batch(connection, data, now)
                self._insert_reservation(connection, data, now)
        if rejected is not None:
            raise rejected

    def _insert_reservation(self, connection: psycopg.Connection[Any], data: dict[str, Any], now: datetime) -> None:
        connection.execute(
            sql.SQL(
                "INSERT INTO {}(account_id,attempt_id,at,provider,model,role,lane,bucket,"
                "run_id,batch_id,scenario_id) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            ).format(self.table("core_model_usage")),
            (
                self.account_id,
                data["attempt_id"],
                now,
                data["provider"],
                data["model"],
                data["role"],
                data["lane"],
                data["bucket"],
                data.get("run_id"),
                data.get("batch_id"),
                data.get("scenario_id"),
            ),
        )

    def stop(
        self,
        connection: psycopg.Connection[Any],
        kind: str,
        now: datetime,
        *,
        resume_at: datetime | None = None,
    ) -> None:
        if kind not in STOP_KINDS:
            raise GuardConfigurationError("中央停止类别无效")
        priority = {
            "member_window_limit": -1,
            "quota": 0,
            "quota_5h": 1,
            "quota_weekly": 2,
            "quota_monthly": 3,
            "concurrency_limited": 4,
            "access_terminated": 5,
        }
        old = self.verify(connection, lock=True)["stop_kind"]
        if old is None or priority[kind] > priority[old]:
            resume = resume_at or (now + timedelta(hours=5) if kind in {"quota_5h", "member_window_limit"} else None)
            connection.execute(
                sql.SQL("UPDATE {} SET stop_kind=%s,stopped_at=%s,resume_at=%s WHERE account_id=%s").format(
                    self.table("core_model_accounts")
                ),
                (kind, now, resume, self.account_id),
            )
        connection.execute(
            sql.SQL("UPDATE {} SET expires_at=least(expires_at,%s) WHERE account_id=%s AND status='active'").format(
                self.table("core_model_batches")
            ),
            (now, self.account_id),
        )

    def finish(
        self,
        connection: psycopg.Connection[Any],
        attempt_id: str,
        kind: str,
        usage: dict[str, Any],
        now: datetime,
        latency_ms: float,
    ) -> None:
        with connection.transaction():
            now = self.finalizing(connection, now)
            row = connection.execute(
                sql.SQL(
                    "UPDATE {} SET status=%s,input_tokens=%s,cache_read_tokens=%s,cache_write_tokens=%s,"
                    "output_tokens=%s,latency_ms=%s,finished_at=%s "
                    "WHERE account_id=%s AND attempt_id=%s AND finished_at IS NULL RETURNING id"
                ).format(self.table("core_model_usage")),
                (
                    kind,
                    usage.get("input_tokens"),
                    usage.get("cache_read_tokens"),
                    usage.get("cache_write_tokens"),
                    usage.get("output_tokens"),
                    latency_ms,
                    now,
                    self.account_id,
                    attempt_id,
                ),
            ).fetchone()
            if row is None:
                raise GuardRejected("attempt_replayed")
            if kind in STOP_KINDS:
                self.stop(connection, kind, now)

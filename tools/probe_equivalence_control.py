"""Explicitly initialized loopback evaluation state; never a Core migration."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from mingjing_core.models.quota_delegated import token_parts
from mingjing_core.models.quota_types import GuardRejected
from tools.eval.targets.local_db import local_dsn, verify_local_postgres


def digest(value: Any) -> str:
    def encode(item: Any) -> str:
        return item.isoformat()

    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=encode).encode()).hexdigest()


class ProbeControlError(ValueError):
    code = "PROBE_CONTROL_REJECTED"


class ProbeControl:
    def __init__(self, dsn: str, schema: str) -> None:
        if re.fullmatch(r"probe_[a-z0-9_]{1,57}", schema or "") is None:
            raise ProbeControlError("评测控制schema必须使用独立probe_前缀")
        self.dsn, self.schema = local_dsn(dsn), schema

    def table(self, name: str) -> sql.Identifier:
        return sql.Identifier(self.schema, name)

    def connect(self) -> psycopg.Connection[Any]:
        verify_local_postgres(self.dsn)
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row, connect_timeout=5)

    def initialize(self) -> None:
        """Only the separate init-control CLI calls DDL, never normal evaluation."""
        with self.connect() as connection, connection.transaction():
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            connection.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {}(evaluation_session_id text PRIMARY KEY,account_id text NOT NULL,"
                    "ledger_identity text NOT NULL,location_id text NOT NULL,control_location_id text NOT NULL,"
                    "candidate_commit text NOT NULL,"
                    "source_sha256 text NOT NULL,contract_sha256 text NOT NULL,"
                    "mode text NOT NULL CHECK(mode IN('live','mock')),"
                    "status text NOT NULL DEFAULT 'active',stop_kind text,resume_at timestamptz,"
                    "prior_attempt_ids text[] NOT NULL,at timestamptz NOT NULL,"
                    "UNIQUE(account_id,ledger_identity,location_id))"
                ).format(self.table("probe_sessions"))
            )
            connection.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {}(evaluation_session_id text NOT NULL "
                    "REFERENCES {}(evaluation_session_id),"
                    "attempt_id text NOT NULL UNIQUE,model text NOT NULL,scenario text NOT NULL,step integer NOT NULL,"
                    "usage_sha256 text NOT NULL,result jsonb NOT NULL,"
                    "PRIMARY KEY(evaluation_session_id,model,scenario,step))"
                ).format(self.table("probe_checks"), self.table("probe_sessions"))
            )

    def location(self, connection: Any) -> str:
        row = connection.execute(
            "SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port"
        ).fetchone()
        return digest({**row, "schema": self.schema})

    def verify(self, connection: Any, guard: Any) -> dict[str, Any]:
        # Both locations are checked independently; a Core schema is never reused.
        verify_local_postgres(guard.store.dsn)
        if self.schema == guard.store.schema:
            raise ProbeControlError("评测控制schema不能复用中央schema")
        for name in ("probe_sessions", "probe_checks"):
            if (
                connection.execute("SELECT to_regclass(%s) AS name", (f'"{self.schema}"."{name}"',)).fetchone()["name"]
                is None
            ):
                raise ProbeControlError("请先显式初始化评测控制schema")
        with guard.store.connect() as central:
            return guard.store.verify(central)

    @contextmanager
    def exclusive(self, guard: Any) -> Iterator[None]:
        verify_local_postgres(guard.store.dsn)
        with guard.store.connect() as central:
            account = guard.store.verify(central)
            key = int.from_bytes(
                hashlib.sha256(
                    f"v7-equivalence:{guard.store.account_id}:{guard.store.identity}:{account['location_id']}".encode()
                ).digest()[:8],
                "big",
                signed=True,
            )
            if not central.execute("SELECT pg_try_advisory_lock(%s) AS held", (key,)).fetchone()["held"]:
                raise GuardRejected("in_flight_limit")
            yield

    def physical(self, guard: Any) -> list[dict[str, Any]]:
        verify_local_postgres(guard.store.dsn)
        with guard.store.connect() as connection:
            guard.store.verify(connection)
            return connection.execute(
                sql.SQL(
                    "SELECT u.*,b.authorization_id FROM {} u LEFT JOIN {} b USING(account_id,batch_id) "
                    "WHERE u.account_id=%s AND u.lane='probe' ORDER BY u.id"
                ).format(guard.store.table("core_model_usage"), guard.store.table("core_model_batches")),
                (guard.store.account_id,),
            ).fetchall()

    def open_session(self, guard: Any, candidate: str, source: str, contract: str, mode: str) -> dict[str, Any]:
        if any(
            re.fullmatch(pattern, value or "") is None
            for pattern, value in (
                (r"[0-9a-f]{40}", candidate),
                (r"[0-9a-f]{64}", source),
                (r"[0-9a-f]{64}", contract),
            )
        ) or mode not in {"live", "mock"}:
            raise ProbeControlError("评测来源无效")
        with self.connect() as connection, connection.transaction():
            account = self.verify(connection, guard)
            keys = (guard.store.account_id, guard.store.identity, account["location_id"])
            old = connection.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE account_id=%s AND ledger_identity=%s AND location_id=%s FOR UPDATE"
                ).format(self.table("probe_sessions")),
                keys,
            ).fetchone()
            if old is not None:
                if (
                    old["candidate_commit"],
                    old["source_sha256"],
                    old["contract_sha256"],
                    old["mode"],
                    old["control_location_id"],
                ) != (candidate, source, contract, mode, self.location(connection)):
                    raise ProbeControlError("同次等价验证来源改变，不能重置预算")
                return old
            return connection.execute(
                sql.SQL(
                    "INSERT INTO {}(evaluation_session_id,account_id,ledger_identity,location_id,control_location_id,"
                    "candidate_commit,source_sha256,contract_sha256,mode,prior_attempt_ids,at) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *"
                ).format(self.table("probe_sessions")),
                (
                    "eq-" + uuid.uuid4().hex,
                    *keys,
                    self.location(connection),
                    candidate,
                    source,
                    contract,
                    mode,
                    [row["attempt_id"] for row in self.physical(guard)],
                    guard.clock.now(),
                ),
            ).fetchone()

    def session(self, guard: Any, session_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            account = self.verify(connection, guard)
            value = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE evaluation_session_id=%s").format(self.table("probe_sessions")),
                (session_id,),
            ).fetchone()
            if value is not None and value["control_location_id"] != self.location(connection):
                raise ProbeControlError("评测控制库定位改变")
        if value is None or (value["account_id"], value["ledger_identity"], value["location_id"]) != (
            guard.store.account_id,
            guard.store.identity,
            account["location_id"],
        ):
            raise ProbeControlError("等价证明中央身份不匹配")
        return value

    def checks(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return connection.execute(
                sql.SQL("SELECT * FROM {} WHERE evaluation_session_id=%s ORDER BY model,scenario,step").format(
                    self.table("probe_checks")
                ),
                (session_id,),
            ).fetchall()

    def record(self, guard: Any, session_id: str, attempt_id: str, result: dict[str, Any]) -> None:
        from psycopg.types.json import Jsonb

        from tools.probe_equivalence_proof import EXPECTED, RESULT_FIELDS

        if (
            set(result) != RESULT_FIELDS
            or type(result["passed"]) is not bool
            or (result["model"], result["scenario"], result["step"]) not in EXPECTED
        ):
            raise ProbeControlError("只允许固定检查的公开结果")

        session = self.session(guard, session_id)
        physical = next((row for row in self.physical(guard) if row["attempt_id"] == attempt_id), None)
        expected_run = f"{session_id}:{result['model']}:{result['scenario']}:{result['step']}"
        if (
            physical is None
            or physical["status"] != "ok"
            or physical["finished_at"] is None
            or physical["model"] != result["model"]
            or physical["scenario_id"] != result["scenario"]
            or physical["run_id"] != expected_run
            or physical["role"] != "evaluation"
            or token_parts(physical["authorization_id"]) != (session["candidate_commit"], "eq")
        ):
            raise ProbeControlError("检查结果与真实调用账本不符")
        with self.connect() as connection:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(evaluation_session_id,attempt_id,model,scenario,step,usage_sha256,result) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s)"
                ).format(self.table("probe_checks")),
                (
                    session_id,
                    attempt_id,
                    result["model"],
                    result["scenario"],
                    result["step"],
                    digest(physical),
                    Jsonb(result),
                ),
            )

    def mark(self, guard: Any, session_id: str, status: str, stop_kind: str | None = None) -> None:
        self.session(guard, session_id)
        state = guard.status()
        with self.connect() as connection:
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET status=%s,stop_kind=%s,resume_at=%s,at=%s WHERE evaluation_session_id=%s"
                ).format(self.table("probe_sessions")),
                (
                    status,
                    stop_kind,
                    state["resume_at"],
                    guard.clock.now(),
                    session_id,
                ),
            )

"""Explicit local PG metadata; private scenario bodies never enter this control store."""

from __future__ import annotations

import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.targets.local_db import local_dsn, verify_local_postgres


class LifecycleControl:
    def __init__(self, dsn: str, schema: str) -> None:
        if re.fullmatch(r"eval_control_[a-z0-9_]{1,49}", schema or "") is None:
            raise LifecycleError("生命周期控制库需要独立eval_control_前缀")
        self.dsn, self.schema = local_dsn(dsn), schema

    def connect(self) -> psycopg.Connection[Any]:
        verify_local_postgres(self.dsn)
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row, connect_timeout=5)

    def table(self) -> sql.Identifier:
        return sql.Identifier(self.schema, "scenario_states")

    def location(self, connection: Any, schema: str | None = None) -> str:
        row = connection.execute(
            "SELECT current_database() AS db,inet_server_addr()::text AS host,inet_server_port() AS port"
        ).fetchone()
        return fingerprint({**row, "schema": schema or self.schema})

    def initialize(self, guard: QuotaGuard) -> None:
        """Explicit setup only. Save/attach refuse an uninitialized control store."""
        verify_local_postgres(guard.store.dsn)
        if self.schema == guard.store.schema:
            raise LifecycleError("生命周期控制库不能复用中央schema")
        with guard.store.connect() as central:
            guard.store.verify(central)
        with self.connect() as connection, connection.transaction():
            connection.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema)))
            connection.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {}(session_id text PRIMARY KEY,binding jsonb NOT NULL,"
                    "control_location text NOT NULL,target_schema text NOT NULL,target_location text NOT NULL,"
                    "state_id text NOT NULL,state_sha256 text NOT NULL,revision bigint NOT NULL)"
                ).format(self.table())
            )

    def _ready(self, connection: Any) -> None:
        row = connection.execute("SELECT to_regclass(%s) AS name", (f'"{self.schema}"."scenario_states"',)).fetchone()
        if row["name"] is None:
            raise LifecycleError("请先显式初始化生命周期控制库")

    def save(
        self,
        session_id: str,
        binding: LifecycleBinding,
        guard: QuotaGuard,
        *,
        target_schema: str,
        target_location: str,
        state_id: str,
        state_sha256: str,
    ) -> dict[str, Any]:
        identity = binding.verify(guard)
        if (
            re.fullmatch(r"eval-[a-f0-9]{32}", session_id) is None
            or re.fullmatch(r"eval_v4_[a-f0-9]{32}", target_schema) is None
            or state_id != "eval-lifecycle:" + session_id
            or re.fullmatch(r"[a-f0-9]{64}", state_sha256) is None
        ):
            raise LifecycleError("生命周期状态定位无效")
        with self.connect() as connection, connection.transaction():
            self._ready(connection)
            old = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE session_id=%s FOR UPDATE").format(self.table()), (session_id,)
            ).fetchone()
            fixed = (identity, self.location(connection), target_schema, target_location, state_id)
            if (
                old
                and tuple(
                    old[key] for key in ("binding", "control_location", "target_schema", "target_location", "state_id")
                )
                != fixed
            ):
                raise LifecycleError("生命周期身份不能覆盖")
            return connection.execute(
                sql.SQL(
                    "INSERT INTO {} VALUES(%s,%s,%s,%s,%s,%s,%s,1) ON CONFLICT(session_id) DO UPDATE "
                    "SET state_sha256=excluded.state_sha256,revision=scenario_states.revision+1 RETURNING *"
                ).format(self.table()),
                (session_id, Jsonb(identity), *fixed[1:], state_sha256),
            ).fetchone()

    def load(self, session_id: str, binding: LifecycleBinding, guard: QuotaGuard) -> dict[str, Any]:
        identity = binding.verify(guard)
        with self.connect() as connection:
            self._ready(connection)
            row = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE session_id=%s").format(self.table()), (session_id,)
            ).fetchone()
            if row is None or row["binding"] != identity or row["control_location"] != self.location(connection):
                raise LifecycleError("生命周期记录不存在或不属于当前身份")
            return row

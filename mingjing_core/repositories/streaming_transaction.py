"""Short stream writes acquire a bounded connection before any owner lock."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg_pool import PoolTimeout

from mingjing_core.domain.contracts import EvidenceError, LeaseConflict

from .postgres import PostgresRepository


def _active(stopped: threading.Event | None) -> None:
    if stopped is not None and stopped.is_set():
        raise LeaseConflict("流式刷新已经停止")


@contextmanager
def streaming_transaction(
    repo: PostgresRepository, owner: str, stopped: threading.Event | None = None
) -> Iterator[Any]:
    previous = getattr(repo._local, "connection", None)
    if previous is not None:
        raise EvidenceError("流式刷新不能加入已有外层事务")
    _active(stopped)
    try:
        with repo.pool.connection(timeout=0.05) as connection, connection.transaction():
            connection.execute("SET LOCAL statement_timeout='100ms'")
            connection.execute("SET LOCAL lock_timeout='25ms'")
            row = connection.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s,0)) AS acquired",
                (repo.schema + ":" + owner,),
            ).fetchone()
            if not row["acquired"]:
                raise LeaseConflict("流式刷新暂时无法取得写入权限")
            repo._local.connection = connection
            try:
                _active(stopped)
                yield connection
                _active(stopped)
            finally:
                repo._local.connection = previous
    except (psycopg.Error, PoolTimeout):
        raise EvidenceError("流式数据库操作未安全完成，本轮已停止") from None

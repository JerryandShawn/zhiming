"""Actual PG timeout, owner lock, nesting and pool return boundaries."""

from __future__ import annotations

import threading
import time

import pytest
from psycopg import sql

from mingjing_core.domain.contracts import EvidenceError, LeaseConflict
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.repositories.streaming_transaction import streaming_transaction


def test_nested_original_services_share_the_bounded_connection(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    with streaming_transaction(repo, "alice") as connection:
        assert repo._local.connection is connection
        with repo.transaction("alice") as nested:
            assert nested is connection
            assert nested.execute("SHOW statement_timeout").fetchone()["statement_timeout"] == "100ms"
            assert nested.execute("SHOW lock_timeout").fetchone()["lock_timeout"] == "25ms"
        assert repo.assert_scope("alice")["id"] == "self"
    assert getattr(repo._local, "connection", None) is None
    with repo.pool.connection(timeout=0.1) as connection:
        assert connection.execute("SHOW statement_timeout").fetchone()["statement_timeout"] != "100ms"


def test_outer_transaction_is_rejected_without_replacing_it(p2_repo: PostgresRepository) -> None:
    with p2_repo.transaction("alice") as original:
        with pytest.raises(EvidenceError, match="已有外层事务"), streaming_transaction(p2_repo, "alice"):
            pytest.fail("an existing outer transaction cannot become a timer transaction")
        assert p2_repo._local.connection is original


def test_contended_owner_lock_is_nonblocking_and_connection_returns(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    with repo.pool.connection() as other, other.transaction():
        other.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (repo.schema + ":alice",))
        started = time.monotonic()
        with pytest.raises(LeaseConflict), streaming_transaction(repo, "alice"):
            pytest.fail("contended writer must not enter")
        assert time.monotonic() - started < 0.3
    assert getattr(repo._local, "connection", None) is None
    with streaming_transaction(repo, "alice"):
        assert repo.get_revision("alice") >= 0


def test_statement_timeout_rolls_back_and_restores_threadlocal(p2_repo: PostgresRepository) -> None:
    started = time.monotonic()
    with (
        pytest.raises(EvidenceError, match="数据库操作未安全完成"),
        streaming_transaction(p2_repo, "alice") as connection,
    ):
        connection.execute("SELECT pg_sleep(0.3)")
    assert time.monotonic() - started < 0.5
    assert getattr(p2_repo._local, "connection", None) is None
    with streaming_transaction(p2_repo, "alice") as connection:
        assert connection.execute("SELECT 1 AS value").fetchone()["value"] == 1


def test_row_lock_timeout_cannot_commit_a_delayed_mutation(p2_repo: PostgresRepository) -> None:
    repo = p2_repo
    before = repo.get_revision("alice")
    with repo.pool.connection() as other, other.transaction():
        other.execute(sql.SQL("SELECT id FROM {} WHERE id='alice' FOR UPDATE").format(repo.table("core_owners")))
        started = time.monotonic()
        with pytest.raises(EvidenceError), streaming_transaction(repo, "alice") as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET revision=revision+1 WHERE id='alice'").format(repo.table("core_owners"))
            )
        assert time.monotonic() - started < 0.3
    assert repo.get_revision("alice") == before
    assert getattr(repo._local, "connection", None) is None


def test_stop_before_commit_rolls_back_real_mutation(p2_repo: PostgresRepository) -> None:
    stopped = threading.Event()
    before = p2_repo.get_revision("alice")
    with pytest.raises(LeaseConflict), streaming_transaction(p2_repo, "alice", stopped) as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET revision=revision+1 WHERE id='alice'").format(p2_repo.table("core_owners"))
        )
        stopped.set()
    assert p2_repo.get_revision("alice") == before
    assert getattr(p2_repo._local, "connection", None) is None


def test_exhausted_pool_is_bounded_and_usable_after_return(p2_repo: PostgresRepository) -> None:
    repo = PostgresRepository(p2_repo.dsn, schema=p2_repo.schema, initialize=False, max_size=1)
    try:
        with repo.pool.connection():
            started = time.monotonic()
            with pytest.raises(EvidenceError), streaming_transaction(repo, "alice"):
                pytest.fail("an exhausted pool cannot enter")
            assert time.monotonic() - started < 0.3
        with streaming_transaction(repo, "alice") as connection:
            assert connection.execute("SELECT 1 AS value").fetchone()["value"] == 1
    finally:
        repo.close()

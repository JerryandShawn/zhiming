"""Four real-PG pool lease boundaries; no source worker, restore, or publication acceptance."""

from __future__ import annotations

from types import SimpleNamespace

import psycopg
import pytest
from langgraph.checkpoint.base import empty_checkpoint
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from test_first_release_incremental_backup_pg import archive, existing  # noqa: F401

from mingjing_core.repositories.postgres import PostgresRepository
from tools.first_release_incremental_pg import snapshot
from tools.first_release_source_pool import (
    ExpectedPoolIdentity,
    PoolLeaseRejected,
    lease_identity,
    pinned_candidate_pool,
    require_idle_lease,
)
from tools.first_release_writer_fence import pg_lock


@pytest.fixture
def pool_case(existing):  # noqa: F811
    dsn = existing.environment["FIRST_INCREMENTAL_OWNER_DSN"]
    fields = conninfo_to_dict(dsn)
    with (
        psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as parent,
        pg_lock(parent, existing.inputs.fence_key, exclusive=True),
    ):
        expected = ExpectedPoolIdentity(
            existing.inputs.operation_id,
            existing.inputs.source,
            fields["host"],
            int(fields["port"]),
            parent.info.backend_pid,
        )
        repo = PostgresRepository(
            make_conninfo(dsn, options="-c search_path=pg_catalog,public -c TimeZone=UTC"),
            initialize=False,
            max_size=1,
        )
        try:
            yield SimpleNamespace(existing=existing, repo=repo, parent=parent, expected=expected)
        finally:
            repo.close()


def source_state(value):
    with value.parent.transaction():
        return snapshot(value.parent)


def checkpoint_counts(repo, thread):
    with repo.transaction() as connection:
        return [
            connection.execute(
                sql.SQL("SELECT count(*) AS n FROM public.{} WHERE thread_id=%s").format(sql.Identifier(name)),
                (thread,),
            ).fetchone()["n"]
            for name in ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
        ]


def assert_closed_without_replacement(value, pool, get_method, put_method):
    assert value.repo.pool is pool and type(pool) is ConnectionPool and pool.closed
    assert pool.get_stats()["connections_num"] == pool.get_stats()["requests_num"] == 1
    assert pool.getconn.__func__ is get_method and pool.putconn.__func__ is put_method


def test_original_repository_nested_transactions_and_real_saver_share_one_physical_connection(pool_case):
    value, repo = pool_case, pool_case.repo
    pool, before = repo.pool, source_state(value)
    get_method, put_method, timeout = pool.getconn.__func__, pool.putconn.__func__, pool.reconnect_timeout
    marker = ValueError("SYNTHETIC_ORDINARY_FAILURE")
    with pytest.raises(ValueError) as ordinary, pinned_candidate_pool(repo, value.expected) as lease:
        initial = lease_identity(lease)
        with repo.transaction() as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            first_snapshot = connection.execute("SELECT txid_current_snapshot()::text AS value").fetchone()["value"]
            with repo.transaction("synthetic") as nested:
                assert nested is connection and nested.info.backend_pid == initial["pid"]
                assert nested.info.transaction_status == TransactionStatus.INTRANS
                assert (
                    nested.execute("SELECT txid_current_snapshot()::text AS value").fetchone()["value"]
                    == first_snapshot
                )
        with pytest.raises(ValueError) as failed, repo.transaction():
            raise marker
        assert failed.value is marker
        saver, thread = PostgresSaver(pool), "synthetic-source-pool:e0"
        checkpoint = empty_checkpoint()
        checkpoint["channel_values"], checkpoint["channel_versions"] = (
            {"synthetic": {"only": "fixture"}},
            {"synthetic": "1"},
        )
        config = saver.put(
            {"configurable": {"thread_id": thread, "checkpoint_ns": ""}}, checkpoint, {}, {"synthetic": "1"}
        )
        saver.put_writes(config, [("synthetic", "SYNTHETIC_POOL_WRITE")], "synthetic-task")
        assert checkpoint_counts(repo, thread) == [1, 1, 1]
        saver.delete_thread(thread)
        assert checkpoint_counts(repo, thread) == [0, 0, 0]
        final = lease_identity(lease)
        assert repo.pool is pool and final["pid"] == initial["pid"]
        assert final["logical_checkouts"] > initial["logical_checkouts"] and final["physical_connections"] == 1
        assert (
            final["source_write_authorized"] is final["sid_verified"] is final["post_pin_replacement_allowed"] is False
        )
        raise marker
    assert ordinary.value is marker
    assert_closed_without_replacement(value, pool, get_method, put_method)
    assert pool.reconnect_timeout == timeout and source_state(value) == before
    with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_LEASE_EXPIRED"):
        require_idle_lease(lease)


def test_closed_held_connection_poison_never_reacquires_or_reconnects(pool_case):
    value, repo = pool_case, pool_case.repo
    pool, before = repo.pool, source_state(value)
    get_method, put_method = pool.getconn.__func__, pool.putconn.__func__
    with (
        pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_CONNECTION_NOT_IDLE"),
        pinned_candidate_pool(repo, value.expected) as lease,
    ):
        connection = pool.getconn()
        pid = connection.info.backend_pid
        connection.close()
        with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_CONNECTION_NOT_IDLE"):
            pool.putconn(connection)
        with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_CONNECTION_NOT_IDLE"):
            require_idle_lease(lease)
    assert_closed_without_replacement(value, pool, get_method, put_method)
    value.parent.execute("SELECT pg_stat_clear_snapshot()")
    observed = value.parent.execute("SELECT pid FROM pg_stat_activity WHERE datname=current_database()").fetchall()
    assert {row["pid"] for row in observed} <= {pid, value.parent.info.backend_pid}
    assert source_state(value) == before


def test_foreign_actual_connection_return_is_rejected_without_owning_or_closing_it(pool_case):
    value, repo = pool_case, pool_case.repo
    pool, before = repo.pool, source_state(value)
    get_method, put_method = pool.getconn.__func__, pool.putconn.__func__
    with (
        pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_FOREIGN_CONNECTION"),
        pinned_candidate_pool(repo, value.expected),
        psycopg.connect(value.existing.environment["FIRST_INCREMENTAL_OWNER_DSN"], autocommit=True) as foreign,
    ):
        with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_FOREIGN_CONNECTION"):
            pool.putconn(foreign)
        assert not foreign.closed and foreign.execute("SELECT 17").fetchone() == (17,)
        with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_FOREIGN_CONNECTION"):
            pool.getconn()
    assert_closed_without_replacement(value, pool, get_method, put_method)
    assert source_state(value) == before


def test_extra_actual_source_session_permanently_burns_the_lease_generation(pool_case):
    value, repo = pool_case, pool_case.repo
    pool, before = repo.pool, source_state(value)
    get_method, put_method = pool.getconn.__func__, pool.putconn.__func__
    with (
        pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_OTHER_SESSION"),
        pinned_candidate_pool(repo, value.expected) as lease,
    ):
        pid = lease_identity(lease)["pid"]
        with psycopg.connect(value.existing.environment["FIRST_INCREMENTAL_OWNER_DSN"], autocommit=True) as other:
            assert other.info.backend_pid not in {pid, value.expected.parent_pid}
            with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_OTHER_SESSION"):
                pool.getconn()
        with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_OTHER_SESSION"):
            require_idle_lease(lease)
    assert_closed_without_replacement(value, pool, get_method, put_method)
    with pytest.raises(PoolLeaseRejected, match="SOURCE_POOL_LEASE_EXPIRED"):
        require_idle_lease(lease)
    assert source_state(value) == before

"""One physical local pool lease, without an enclosing business transaction or source-write authority."""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, NoReturn

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from tools.first_release_incremental import SourcePin


class PoolLeaseRejected(BaseException):
    """A finite control stop must escape candidate helpers which catch ordinary Exception."""


def _require(value: Any, code: str) -> None:
    if not value:
        raise PoolLeaseRejected(code)


@dataclass(frozen=True)
class ExpectedPoolIdentity:
    operation_id: str
    source: SourcePin
    host: str
    port: int
    parent_pid: int

    def validate(self) -> None:
        _require(type(self) is ExpectedPoolIdentity and type(self.source) is SourcePin, "SOURCE_POOL_TYPED_IDENTITY")
        _require(
            isinstance(self.operation_id, str)
            and re.fullmatch(r"fr-[0-9a-f]{32}", self.operation_id)
            and self.source.database == "fr_upgrade_" + self.operation_id[3:],
            "SOURCE_POOL_LOCAL_OPERATION",
        )
        _require(
            type(self.host) is str
            and self.host in {"127.0.0.1", "::1"}
            and type(self.port) is int
            and self.port in {55480, 55481}
            and type(self.parent_pid) is int
            and 0 < self.parent_pid < 2**31,
            "SOURCE_POOL_LOCAL_LOCATION",
        )
        _require(
            isinstance(self.source.system_identifier, str)
            and re.fullmatch(r"[0-9]{15,20}", self.source.system_identifier)
            and all(
                type(value) is int and 0 < value < 2**32
                for value in (self.source.database_oid, self.source.owner_oid, self.source.writer_oid)
            )
            and self.source.owner_oid != self.source.writer_oid,
            "SOURCE_POOL_IMMUTABLE_SOURCE_IDENTITY",
        )
        _require(
            type(self.source.owners) is tuple
            and self.source.owners
            and all(isinstance(owner, str) and 0 < len(owner) <= 200 for owner in self.source.owners)
            and tuple(sorted(set(self.source.owners))) == self.source.owners
            and type(self.source.migrations) is tuple
            and len(self.source.migrations) in {4, 7}
            and all(type(row) is tuple and len(row) == 2 for row in self.source.migrations)
            and [row[0] for row in self.source.migrations]
            == [str(version) for version in range(1, len(self.source.migrations) + 1)]
            and all(
                isinstance(row[1], str) and re.fullmatch(r"[0-9a-f]{64}", row[1]) for row in self.source.migrations
            ),
            "SOURCE_POOL_IMMUTABLE_SOURCE_PROFILE",
        )


_SEAL = object()


class PinnedPoolLease:
    __slots__ = ()

    def __new__(cls, seal: object = None):
        _require(cls is PinnedPoolLease and seal is _SEAL, "SOURCE_POOL_OPAQUE_LEASE_REQUIRED")
        return object.__new__(cls)

    def __repr__(self) -> str:
        return "<PinnedPoolLease>"

    def __reduce__(self) -> Any:
        raise PoolLeaseRejected("SOURCE_POOL_LEASE_NOT_SERIALIZABLE")


@dataclass
class _Lease:
    repo: Any = field(repr=False)
    pool: Any = field(repr=False)
    connection: Any = field(repr=False)
    expected: ExpectedPoolIdentity
    original_get: Any = field(repr=False)
    original_put: Any = field(repr=False)
    original_close: Any = field(repr=False)
    reconnect_timeout: float
    thread: int = field(default_factory=threading.get_ident)
    lock: Any = field(default_factory=threading.Lock, repr=False)
    active: bool = True
    borrowed: bool = False
    poison: PoolLeaseRejected | None = field(default=None, repr=False)
    birth: tuple[Any, ...] | None = None
    checkouts: int = 0
    get_wrapper: Any = field(default=None, repr=False)
    put_wrapper: Any = field(default=None, repr=False)

    def stop(self, code: str) -> NoReturn:
        if self.poison is None:
            self.poison = PoolLeaseRejected(code)
        with suppress(Exception):
            self.original_close()
        raise self.poison

    def require(self, value: Any, code: str) -> None:
        if not value:
            self.stop(code)

    def structure(self) -> None:
        if self.poison is not None:
            raise self.poison
        self.require(self.active and threading.get_ident() == self.thread, "SOURCE_POOL_THREAD_OR_GENERATION")
        self.require(
            self.repo.pool is self.pool
            and not self.pool.closed
            and self.pool.getconn is self.get_wrapper
            and self.pool.putconn is self.put_wrapper
            and getattr(self.pool.connection, "__func__", None) is ConnectionPool.connection
            and self.pool.min_size == 0
            and self.pool.max_size == 1,
            "SOURCE_POOL_INSTANCE_CHANGED",
        )
        c = self.connection
        self.require(
            type(c) is psycopg.Connection
            and not c.closed
            and not c.broken
            and c.autocommit is True
            and c.row_factory is dict_row
            and c.info.transaction_status == TransactionStatus.IDLE,
            "SOURCE_POOL_CONNECTION_NOT_IDLE",
        )
        stats = self.pool.get_stats()
        self.require(
            stats["pool_size"] == stats.get("connections_num") == stats.get("requests_num") == 1
            and stats["pool_available"] == stats["requests_waiting"] == 0,
            "SOURCE_POOL_PHYSICAL_LEASE_CHANGED",
        )

    def identity(self) -> None:
        self.structure()
        c, expected = self.connection, self.expected
        try:
            row = c.execute(
                "SELECT pg_catalog.pg_backend_pid() AS pid,pg_catalog.current_database() AS database,"
                "current_user AS role,session_user AS session_role,"
                "pg_catalog.host(pg_catalog.inet_server_addr()) AS host,pg_catalog.inet_server_port() AS port,"
                "pg_catalog.current_setting('server_version_num')::int AS version,d.oid,d.datdba,"
                "(SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user) AS role_oid,"
                "(SELECT backend_start FROM pg_catalog.pg_stat_activity "
                "WHERE pid=pg_catalog.pg_backend_pid()) AS backend_start "
                "FROM pg_catalog.pg_database d WHERE datname=pg_catalog.current_database()"
            ).fetchone()
            actual = (row["pid"], row["backend_start"])
            self.require(
                (
                    row["database"],
                    row["role"],
                    row["session_role"],
                    row["host"],
                    row["port"],
                    row["oid"],
                    row["datdba"],
                    row["role_oid"],
                )
                == (
                    expected.source.database,
                    expected.source.database + "_owner",
                    expected.source.database + "_owner",
                    expected.host,
                    expected.port,
                    expected.source.database_oid,
                    expected.source.owner_oid,
                    expected.source.owner_oid,
                )
                and 150000 <= row["version"] < 160000
                and row["pid"] == c.info.backend_pid != expected.parent_pid
                and row["backend_start"] is not None
                and (self.birth is None or self.birth == actual),
                "SOURCE_POOL_ACTUAL_IDENTITY_CHANGED",
            )
            self.fence_and_sessions()
            self.birth = actual
        except Exception:
            self.stop("SOURCE_POOL_ACTUAL_CHECK_FAILED")

    def fence_and_sessions(self) -> None:
        c, expected = self.connection, self.expected
        key = "first-release-writer:" + expected.source.system_identifier + ":" + str(expected.source.database_oid)
        locked = c.execute(
            "WITH key AS (SELECT pg_catalog.hashtextextended(%s,0) AS value) "
            "SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_locks,key WHERE locktype='advisory' "
            "AND database=%s AND pid=%s AND mode='ExclusiveLock' AND granted "
            "AND classid::bigint=((key.value>>32)&4294967295) "
            "AND objid::bigint=(key.value&4294967295) AND objsubid=1) AS locked",
            (key, expected.source.database_oid, expected.parent_pid),
        ).fetchone()
        self.require(locked and locked["locked"], "SOURCE_POOL_PARENT_FENCE_MISSING")
        c.execute("SELECT pg_catalog.pg_stat_clear_snapshot()")
        actual = c.execute(
            "SELECT pid FROM pg_catalog.pg_stat_activity WHERE datname=pg_catalog.current_database()"
        ).fetchall()
        self.require(
            {row["pid"] for row in actual} == {expected.parent_pid, c.info.backend_pid},
            "SOURCE_POOL_OTHER_SESSION",
        )

    def getconn(self, timeout: float | None = None) -> Any:
        self.require(threading.get_ident() == self.thread, "SOURCE_POOL_THREAD_OR_GENERATION")
        self.require(self.lock.acquire(blocking=False), "SOURCE_POOL_CONCURRENT_BORROW")
        try:
            self.require(not self.borrowed, "SOURCE_POOL_NESTED_LOGICAL_BORROW")
            self.identity()
            self.borrowed = True
            self.checkouts += 1
            return self.connection
        finally:
            self.lock.release()

    def putconn(self, connection: Any) -> None:
        self.require(threading.get_ident() == self.thread, "SOURCE_POOL_THREAD_OR_GENERATION")
        self.require(self.lock.acquire(blocking=False), "SOURCE_POOL_CONCURRENT_BORROW")
        try:
            self.require(connection is self.connection, "SOURCE_POOL_FOREIGN_CONNECTION")
            self.require(self.borrowed, "SOURCE_POOL_UNPAIRED_RETURN")
            self.identity()
            self.borrowed = False
        finally:
            self.lock.release()


_LEASES: dict[PinnedPoolLease, _Lease] = {}


def _lookup(lease: PinnedPoolLease) -> _Lease:
    _require(type(lease) is PinnedPoolLease, "SOURCE_POOL_OPAQUE_LEASE_REQUIRED")
    record = _LEASES.get(lease)
    _require(record is not None and record.active, "SOURCE_POOL_LEASE_EXPIRED")
    return record


def require_idle_lease(lease: PinnedPoolLease) -> None:
    record = _lookup(lease)
    record.require(not record.borrowed, "SOURCE_POOL_NESTED_LOGICAL_BORROW")
    record.identity()


def lease_identity(lease: PinnedPoolLease) -> dict[str, Any]:
    require_idle_lease(lease)
    record = _lookup(lease)
    return dict(
        operation_id=record.expected.operation_id,
        database_oid=record.expected.source.database_oid,
        owner_oid=record.expected.source.owner_oid,
        pid=record.birth[0],
        logical_checkouts=record.checkouts,
        physical_connections=1,
        source_write_authorized=False,
        sid_verified=False,
        post_pin_replacement_allowed=False,
        initial_connect_failure_tested=False,
    )


def _fresh_pool(repo: Any) -> Any:
    from mingjing_core.repositories.postgres import PostgresRepository

    _require(type(repo) is PostgresRepository, "SOURCE_POOL_REAL_REPOSITORY_REQUIRED")
    pool = repo.pool
    _require(type(pool) is ConnectionPool and not pool.closed, "SOURCE_POOL_REAL_OPEN_POOL_REQUIRED")
    _require(
        pool.min_size == 0
        and pool.max_size == 1
        and pool.close_returns is False
        and pool.connection_class is psycopg.Connection
        and all(getattr(pool, name) is None for name in ("_check", "_configure", "_reset"))
        and getattr(repo._local, "connection", None) is None
        and all(name not in vars(pool) for name in ("getconn", "putconn", "connection", "close")),
        "SOURCE_POOL_FRESH_UNMODIFIED_POOL_REQUIRED",
    )
    stats = pool.get_stats()
    _require(
        stats["pool_size"] == stats["pool_available"] == stats["requests_waiting"] == 0
        and stats.get("requests_num", 0) == stats.get("connections_num", 0) == 0,
        "SOURCE_POOL_UNUSED_POOL_REQUIRED",
    )
    return pool


def _process_control(error: BaseException | None) -> bool:
    return isinstance(error, (KeyboardInterrupt, SystemExit, GeneratorExit))


def _finish(record: _Lease) -> BaseException | None:
    error = None
    try:
        record.original_close()
        _require(record.pool.closed, "SOURCE_POOL_CLOSE_FAILED")
        record.original_put(record.connection)
    except BaseException as failure:
        error = failure if _process_control(failure) else PoolLeaseRejected("SOURCE_POOL_RELEASE_FAILED")
        try:
            record.connection.close()
        except BaseException as later:
            if _process_control(later):
                error = later
    finally:
        record.active = False
        record.pool.reconnect_timeout = record.reconnect_timeout
        vars(record.pool).pop("getconn", None)
        vars(record.pool).pop("putconn", None)
    return error


@contextmanager
def pinned_candidate_pool(repo: Any, expected: ExpectedPoolIdentity) -> Iterator[PinnedPoolLease]:
    _require(type(expected) is ExpectedPoolIdentity, "SOURCE_POOL_TYPED_IDENTITY")
    expected.validate()
    pool = _fresh_pool(repo)
    original_get, original_put, original_close = pool.getconn, pool.putconn, pool.close
    reconnect_timeout = pool.reconnect_timeout
    pool.reconnect_timeout = 0
    try:
        connection = original_get()
    except BaseException as error:
        closing_failure = None
        try:
            original_close()
        except BaseException as later:
            closing_failure = later
        finally:
            pool.reconnect_timeout = reconnect_timeout
        if _process_control(closing_failure):
            raise closing_failure from error
        if _process_control(error):
            raise
        raise PoolLeaseRejected("SOURCE_POOL_INITIAL_ACQUIRE_FAILED") from None
    record = _Lease(repo, pool, connection, expected, original_get, original_put, original_close, reconnect_timeout)
    record.get_wrapper, record.put_wrapper = record.getconn, record.putconn
    pool.getconn, pool.putconn = record.get_wrapper, record.put_wrapper
    lease = PinnedPoolLease(_SEAL)
    _LEASES[lease] = record
    failure = None
    try:
        record.identity()
        yield lease
        record.require(not record.borrowed, "SOURCE_POOL_OUTSTANDING_LOGICAL_BORROW")
    except BaseException as error:
        failure = error
    finally:
        cleanup = _finish(record)
        _LEASES.pop(lease, None)
    # A later real interrupt must not be hidden by a prior gate or ordinary failure.
    if _process_control(cleanup):
        raise cleanup
    if _process_control(failure):
        raise failure
    if record.poison is not None:
        raise record.poison
    if failure is not None:
        raise failure
    if cleanup is not None:
        raise cleanup

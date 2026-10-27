"""Read-only M1 activity visibility bound to the live source and control connections."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

import psycopg

from tools.first_release_contracts import RestoreRejected, require
from tools.first_release_incremental import BackupInputs


@dataclass(frozen=True, repr=False)
class _Observer:
    owner: psycopg.Connection
    admin: psycopg.Connection
    inputs: BackupInputs
    fields: tuple[tuple[str, str], ...]
    owner_pid: int
    admin_pid: int

    def check(self, connection: Any) -> None:
        from tools.first_release_incremental_pg import admin_identity, identity

        require(
            connection is self.owner
            and not self.owner.closed
            and not self.admin.closed
            and self.owner.info.backend_pid == self.owner_pid
            and self.admin.info.backend_pid == self.admin_pid
            and self.admin.autocommit is True,
            "INCREMENTAL_SESSION_OBSERVER_BINDING",
        )
        try:
            require(
                identity(self.owner, self.inputs, "owner") == self.owner_pid
                and admin_identity(self.admin, self.inputs, dict(self.fields)) == self.admin_pid,
                "INCREMENTAL_SESSION_OBSERVER_IDENTITY",
            )
            owner_mode = self.owner.execute(
                "SELECT pg_catalog.current_setting('transaction_read_only') AS read_only"
            ).fetchone()
            require(owner_mode and owner_mode["read_only"] == "on", "INCREMENTAL_SESSION_OBSERVER_OWNER_READONLY")
            visibility = self.admin.execute(
                "SELECT pg_catalog.current_setting('transaction_read_only') AS read_only,"
                "rolsuper OR pg_catalog.pg_has_role(current_user,'pg_read_all_stats','USAGE') AS visible "
                "FROM pg_catalog.pg_roles WHERE rolname=current_user"
            ).fetchone()
            require(
                visibility and visibility["read_only"] == "on" and visibility["visible"] is True,
                "INCREMENTAL_SESSION_OBSERVER_VISIBILITY",
            )
        except psycopg.Error:
            raise RestoreRejected("INCREMENTAL_SESSION_OBSERVER_QUERY_FAILED") from None

    def rows(self, connection: Any) -> list[dict[str, Any]]:
        self.check(connection)
        try:
            self.admin.execute("SELECT pg_catalog.pg_stat_clear_snapshot()")
            rows = self.admin.execute(
                "SELECT pid,backend_type FROM pg_catalog.pg_stat_activity WHERE datid=%s ORDER BY pid",
                (self.inputs.source.database_oid,),
            ).fetchall()
        except psycopg.Error:
            raise RestoreRejected("INCREMENTAL_SESSION_OBSERVER_QUERY_FAILED") from None
        require(
            all(
                type(row["pid"]) is int
                and row["pid"] > 0
                and type(row["backend_type"]) is str
                and 0 < len(row["backend_type"]) <= 64
                for row in rows
            ),
            "INCREMENTAL_SESSION_OBSERVER_VISIBILITY",
        )
        return rows


_CURRENT: ContextVar[_Observer | None] = ContextVar("first_release_m1_session_observer", default=None)


@contextmanager
def observe_source_sessions(
    owner: psycopg.Connection,
    admin: psycopg.Connection,
    inputs: BackupInputs,
    fields: dict[str, str],
) -> Iterator[None]:
    require(
        isinstance(owner, psycopg.Connection)
        and isinstance(admin, psycopg.Connection)
        and not owner.closed
        and not admin.closed
        and type(inputs) is BackupInputs
        and inputs.local_drill is True
        and type(fields) is dict
        and fields.get("dbname") in {"postgres", "core_test_main"}
        and all(type(fields.get(key)) is str for key in ("dbname", "user", "host", "port"))
        and _CURRENT.get() is None,
        "INCREMENTAL_SESSION_OBSERVER_SCOPE",
    )
    fields = {key: fields[key] for key in ("dbname", "user", "host", "port")}
    observer = _Observer(
        owner, admin, inputs, tuple(sorted(fields.items())), owner.info.backend_pid, admin.info.backend_pid
    )
    observer.check(owner)
    token = _CURRENT.set(observer)
    try:
        yield None
    finally:
        _CURRENT.reset(token)


def observed_rows(connection: Any) -> list[dict[str, Any]] | None:
    observer = _CURRENT.get()
    return None if observer is None else observer.rows(connection)

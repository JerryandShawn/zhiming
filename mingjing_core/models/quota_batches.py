"""Explicit, expiring batch grants; restarting a coordinator never starts a batch."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import sql

from mingjing_core.repositories.postgres import fingerprint

from .quota_store import QuotaStore
from .quota_types import (
    GuardConfigurationError,
    GuardRejected,
    QuotaPolicy,
    identifier,
    instant,
)


def begin_batch(
    store: QuotaStore,
    policy: QuotaPolicy,
    now: datetime,
    *,
    batch_id: str,
    scenario_ids: list[str],
    authorization_id: str,
    expires_at: datetime,
) -> None:
    digest, expires_at = _batch_digest(batch_id, scenario_ids, authorization_id, expires_at, now)
    with store.connect() as connection, connection.transaction():
        _begin_locked(connection, store, now, batch_id, scenario_ids, authorization_id, expires_at, digest)


def _batch_digest(
    batch_id: str, scenario_ids: list[str], authorization_id: str, expires_at: datetime, now: datetime
) -> tuple[str, datetime]:
    identifier(batch_id)
    identifier(authorization_id)
    expires_at = instant(expires_at)
    if (
        not isinstance(scenario_ids, list)
        or not 1 <= len(scenario_ids) <= 10
        or any(not isinstance(value, str) for value in scenario_ids)
        or len(set(scenario_ids)) != len(scenario_ids)
    ):
        raise GuardConfigurationError("每批需要一至十个不同场景")
    for scenario in scenario_ids:
        identifier(scenario)
    if expires_at <= now:
        raise GuardRejected("authorization_expired")
    return fingerprint(scenario_ids), expires_at


def _begin_locked(
    connection: Any,
    store: QuotaStore,
    now: datetime,
    batch_id: str,
    scenario_ids: list[str],
    authorization_id: str,
    expires_at: datetime,
    digest: str,
) -> None:
    account = store.locked(connection, now)
    active = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE account_id=%s AND status='active'").format(store.table("core_model_batches")),
        (store.account_id,),
    ).fetchone()
    if active and active["batch_id"] != batch_id:
        raise GuardRejected("batch_conflict")
    old = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE account_id=%s AND batch_id=%s").format(store.table("core_model_batches")),
        (store.account_id, batch_id),
    ).fetchone()
    if old and (old["fingerprint"] != digest or old["status"] != "active"):
        raise GuardRejected("batch_conflict")
    grant = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE account_id=%s AND authorization_id=%s").format(
            store.table("core_model_authorizations")
        ),
        (store.account_id, authorization_id),
    ).fetchone()
    if grant:
        if (
            not old
            or grant["batch_id"] != batch_id
            or old["authorization_id"] != authorization_id
            or grant["expires_at"] != expires_at
        ):
            raise GuardRejected("manual_start_required")
        return
    if not old and account["next_batch_not_before"] and now < account["next_batch_not_before"]:
        raise GuardRejected("batch_cooldown", account["next_batch_not_before"])
    _write_grant(
        connection,
        store,
        batch_id,
        scenario_ids,
        digest,
        authorization_id,
        expires_at,
        now,
    )


def _write_grant(
    connection: Any,
    store: QuotaStore,
    batch_id: str,
    scenarios: list[str],
    digest: str,
    authorization: str,
    expires: datetime,
    now: datetime,
) -> None:
    connection.execute(
        sql.SQL(
            "INSERT INTO {}(account_id,batch_id,scenario_ids,fingerprint,authorization_id,"
            "expires_at,status,started_at) "
            "VALUES(%s,%s,%s,%s,%s,%s,'active',%s) ON CONFLICT(account_id,batch_id) "
            "DO UPDATE SET authorization_id=EXCLUDED.authorization_id,expires_at=EXCLUDED.expires_at"
        ).format(store.table("core_model_batches")),
        (store.account_id, batch_id, scenarios, digest, authorization, expires, now),
    )
    connection.execute(
        sql.SQL(
            "INSERT INTO {}(account_id,authorization_id,batch_id,created_at,expires_at) VALUES(%s,%s,%s,%s,%s)"
        ).format(store.table("core_model_authorizations")),
        (store.account_id, authorization, batch_id, now, expires),
    )


def finish_batch(
    store: QuotaStore,
    policy: QuotaPolicy,
    now: datetime,
    batch_id: str,
    authorization_id: str,
) -> None:
    identifier(batch_id)
    identifier(authorization_id)
    with store.connect() as connection, connection.transaction():
        store.locked(connection, now, stopped=True)
        batch = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE account_id=%s AND batch_id=%s").format(store.table("core_model_batches")),
            (store.account_id, batch_id),
        ).fetchone()
        if batch is None or batch["authorization_id"] != authorization_id:
            raise GuardRejected("manual_start_required")
        if batch["status"] == "completed":
            return
        pending = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE account_id=%s AND batch_id=%s AND finished_at IS NULL LIMIT 1").format(
                store.table("core_model_usage")
            ),
            (store.account_id, batch_id),
        ).fetchone()
        if pending:
            raise GuardRejected("in_flight_limit")
        connection.execute(
            sql.SQL("UPDATE {} SET status='completed',finished_at=%s WHERE account_id=%s AND batch_id=%s").format(
                store.table("core_model_batches")
            ),
            (now, store.account_id, batch_id),
        )
        connection.execute(
            sql.SQL("UPDATE {} SET next_batch_not_before=%s WHERE account_id=%s").format(
                store.table("core_model_accounts")
            ),
            (now + policy.batch_gap, store.account_id),
        )


def close_abandoned_batch(
    connection: Any, store: QuotaStore, policy: QuotaPolicy, now: datetime, batch_id: str, recovery: str
) -> None:
    """Caller holds both session slots; never refund or replay unknown sends."""
    identifier(batch_id)
    identifier(recovery)
    with connection.transaction():
        store.locked(connection, now, stopped=True)
        batch = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE account_id=%s AND batch_id=%s").format(store.table("core_model_batches")),
            (store.account_id, batch_id),
        ).fetchone()
        if batch is None:
            raise GuardRejected("batch_conflict")
        if batch["status"] == "completed":
            if batch["recovery_authorization"] != recovery:
                raise GuardRejected("batch_conflict")
            return
        if recovery == batch["authorization_id"]:
            raise GuardRejected("manual_start_required")
        if not store.control_action(connection, recovery, "recovery", batch_id, now):
            raise GuardRejected("batch_conflict")
        updated = connection.execute(
            sql.SQL(
                "UPDATE {} SET status='unknown',finished_at=%s WHERE account_id=%s AND batch_id=%s "
                "AND finished_at IS NULL RETURNING id"
            ).format(store.table("core_model_usage")),
            (now, store.account_id, batch_id),
        ).fetchall()
        if not updated:
            raise GuardRejected("batch_conflict")
        connection.execute(
            sql.SQL(
                "UPDATE {} SET status='completed',finished_at=%s,recovery_authorization=%s "
                "WHERE account_id=%s AND batch_id=%s"
            ).format(store.table("core_model_batches")),
            (now, recovery, store.account_id, batch_id),
        )
        connection.execute(
            sql.SQL("UPDATE {} SET next_batch_not_before=%s WHERE account_id=%s").format(
                store.table("core_model_accounts")
            ),
            (now + policy.batch_gap, store.account_id),
        )

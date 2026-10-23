"""Central account membership admissions, persistent stops and session-owned slots.

The integration point is immediately before each physical POST, after request
preflight. Construction never infers a business DB or provisions an account.
Unknown/crashed reservations remain charged conservatively; no automatic resume.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from psycopg import sql

from mingjing_core.timekit.clock import Clock, SystemClock

from .error_actions import NEVER
from .errors import ModelCancelled, ModelUnavailable
from .quota_batches import begin_batch, close_abandoned_batch, finish_batch
from .quota_mode import verified_delegated_attempt
from .quota_store import QuotaStore
from .quota_types import (
    RESULT_KINDS,
    GuardConfigurationError,
    GuardRejected,
    QuotaPolicy,
    bucket,
    identifier,
    instant,
)


def _usage(value: Mapping[str, Any]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for key in (
        "input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "output_tokens",
    ):
        item = value.get(key)
        result[key] = item if type(item) is int and 0 <= item <= 2**63 - 1 else None
    return result


@dataclass
class Attempt:
    attempt_id: str
    kind: str = "ok"
    usage: dict[str, int | None] = field(default_factory=dict)
    resume_at: datetime | None = None

    def result(self, *, kind: str = "ok", usage: Mapping[str, Any] | None = None) -> None:
        if kind not in RESULT_KINDS:
            raise GuardConfigurationError("调用结果类别无效")
        self.kind, self.usage = kind, _usage(usage or {})


class QuotaGuard:
    def __init__(
        self,
        *,
        central_dsn: str,
        central_schema: str,
        account_id: str,
        ledger_identity: str,
        clock: Clock | None = None,
        policy: QuotaPolicy | None = None,
    ) -> None:
        self.store = QuotaStore(central_dsn, central_schema, account_id, ledger_identity)
        # Scenario clocks must never backdate financial admission or authorization.
        self.clock, self.policy = clock or SystemClock(), policy or QuotaPolicy()
        with self.store.connect() as connection:
            self.store.verify(connection)

    def _key(self, slot: int) -> int:
        value = f"mingjing-member:{self.store.schema}:{self.store.account_id}:{self.store.identity}:{slot}"
        return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)

    def _available(self, connection: Any) -> None:
        account = self.store.verify(connection)
        if account["stop_kind"]:
            raise GuardRejected(account["stop_kind"], account["resume_at"])

    def _slot(
        self,
        connection: Any,
        category: str,
        timeout: float | None,
        cancel: threading.Event | None,
    ) -> int:
        if timeout is not None and (type(timeout) not in (int, float) or not 0 <= timeout <= 3600):
            raise GuardConfigurationError("中央守卫等待时间无效")
        timeout = min(10, 10 if timeout is None else timeout) if category == "interactive" else timeout
        deadline = None if timeout is None else time.monotonic() + timeout
        slots = (0, 1) if category == "interactive" else (1,)
        while True:
            self._available(connection)
            if cancel is not None and cancel.is_set():
                raise ModelCancelled()
            for slot in slots:
                if connection.execute("SELECT pg_try_advisory_lock(%s) AS held", (self._key(slot),)).fetchone()["held"]:
                    return slot
            if deadline is not None and time.monotonic() >= deadline:
                raise GuardRejected("in_flight_limit")
            time.sleep(0.02)

    @contextmanager
    def acquire(
        self,
        role: str,
        lane: str,
        *,
        attempt_id: str,
        provider: str,
        model: str,
        run_id: str | None = None,
        batch_id: str | None = None,
        authorization_id: str | None = None,
        scenario_id: str | None = None,
        timeout: float | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Iterator[Attempt]:
        data = {
            "attempt_id": identifier(attempt_id),
            "provider": identifier(provider),
            "model": identifier(model),
            "role": role,
            "lane": lane,
            "bucket": bucket(role, lane),
            "run_id": run_id,
            "batch_id": batch_id,
            "authorization_id": authorization_id,
            "scenario_id": scenario_id,
        }
        for value in (run_id, batch_id, authorization_id, scenario_id):
            if value is not None:
                identifier(value)
        with self._attempt(data, timeout, cancel_event) as attempt:
            yield attempt

    @contextmanager
    def _attempt(
        self,
        data: dict[str, Any],
        timeout: float | None,
        cancel_event: threading.Event | None,
    ) -> Iterator[Attempt]:
        # Dedicated session closure releases its advisory slot even when finish fails.
        with self.store.connect() as connection:
            self._slot(connection, data["bucket"], timeout, cancel_event)
            self.store.reserve(connection, data, instant(self.clock.now()), self.policy)
            from .quota_delegated import token_parts

            delegated = token_parts(data.get("authorization_id")) is not None
            attempt, started = Attempt(data["attempt_id"]), time.monotonic()
            try:
                with verified_delegated_attempt(delegated, self.clock):
                    yield attempt
            except BaseException as error:
                kind = getattr(
                    error,
                    "kind",
                    "cancelled" if isinstance(error, KeyboardInterrupt) else "unknown",
                )
                attempt.kind = kind if kind in RESULT_KINDS else "unknown"
                attempt.resume_at = getattr(error, "provider_reset_at", None)
                if delegated and isinstance(error, Exception):
                    if isinstance(error, ModelUnavailable):
                        if not error.global_stop:
                            error.retry_actions = NEVER
                    else:
                        raise ModelUnavailable(retry_actions=NEVER) from None
                raise
            finally:
                self.store.finish(
                    connection,
                    data["attempt_id"],
                    attempt.kind,
                    attempt.usage,
                    instant(self.clock.now()),
                    (time.monotonic() - started) * 1000,
                    resume_at=attempt.resume_at,
                )

    def begin_batch(
        self,
        *,
        batch_id: str,
        scenario_ids: list[str],
        authorization_id: str,
        expires_at: datetime,
    ) -> None:
        begin_batch(
            self.store,
            self.policy,
            instant(self.clock.now()),
            batch_id=batch_id,
            scenario_ids=scenario_ids,
            authorization_id=authorization_id,
            expires_at=expires_at,
        )

    def finish_batch(self, batch_id: str, authorization_id: str) -> None:
        finish_batch(
            self.store,
            self.policy,
            instant(self.clock.now()),
            batch_id,
            authorization_id,
        )

    def close_abandoned_batch(self, *, batch_id: str, recovery_authorization_id: str) -> None:
        """Trusted, explicit manual recovery only; this never starts another batch."""
        with self.store.connect() as connection:
            for slot in (0, 1):
                if not connection.execute("SELECT pg_try_advisory_lock(%s) AS held", (self._key(slot),)).fetchone()[
                    "held"
                ]:
                    raise GuardRejected("in_flight_limit")
            close_abandoned_batch(
                connection,
                self.store,
                self.policy,
                instant(self.clock.now()),
                batch_id,
                recovery_authorization_id,
            )

    def record_stop(self, kind: str, *, resume_at: datetime | None = None) -> None:
        with self.store.connect() as connection, connection.transaction():
            now = self.store.finalizing(connection, instant(self.clock.now()))
            self.store.stop(connection, kind, now, resume_at=resume_at)

    def clear_stop(self, *, authorization_id: str) -> None:
        """Only a trusted manual control may invoke this; it never grants a batch."""
        identifier(authorization_id)
        with self.store.connect() as connection, connection.transaction():
            now = instant(self.clock.now())
            account = self.store.locked(connection, now, stopped=True)
            if not self.store.control_action(connection, authorization_id, "clear_stop", None, now):
                return
            if not account["stop_kind"]:
                return
            if account["stop_kind"] in {"quota_5h", "member_window_limit"} and (
                account["resume_at"] is None or now < account["resume_at"]
            ):
                raise GuardRejected(account["stop_kind"], account["resume_at"])
            connection.execute(
                sql.SQL(
                    "UPDATE {} SET stop_kind=NULL,stopped_at=NULL,resume_at=NULL,clear_authorization=%s "
                    "WHERE account_id=%s"
                ).format(self.store.table("core_model_accounts")),
                (authorization_id, self.store.account_id),
            )
            connection.execute(
                sql.SQL("UPDATE {} SET expires_at=least(expires_at,%s) WHERE account_id=%s AND status='active'").format(
                    self.store.table("core_model_batches")
                ),
                (now, self.store.account_id),
            )

    def status(self) -> dict[str, Any]:
        with self.store.connect() as connection:
            account = self.store.verify(connection)
            now = instant(self.clock.now())
            if account["last_clock_at"] is not None and now < account["last_clock_at"]:
                raise GuardRejected("clock_rollback")
            counts = self.store.counts(connection, now, self.policy)
            governed = self.store.counts(connection, now, self.policy, governed=True)
            in_flight = 0
            for slot in (0, 1):
                held = connection.execute("SELECT pg_try_advisory_lock(%s) AS held", (self._key(slot),)).fetchone()[
                    "held"
                ]
                if held:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (self._key(slot),))
                else:
                    in_flight += 1
        return {
            "ledger_identity": self.store.identity,
            "account_id": self.store.account_id,
            "window": counts,
            "remaining_total": max(0, self.policy.max_calls - governed["total"]),
            "remaining": {
                name: max(0, self.policy.limit(name) - governed[name])
                for name in ("interactive", "critic", "background")
            },
            "in_flight": in_flight,
            "stop_kind": account["stop_kind"],
            "stopped_at": account["stopped_at"],
            "resume_at": account["resume_at"],
            "next_batch_not_before": account["next_batch_not_before"],
            "automatic_resume": False,
        }

    def critic_allowed(self) -> bool:
        state = self.status()
        return not state["stop_kind"] and state["remaining_total"] > 0 and state["remaining"]["critic"] > 0

    def background_allowed(self) -> bool:
        state = self.status()
        return not state["stop_kind"] and state["remaining_total"] > 0 and state["remaining"]["background"] > 0

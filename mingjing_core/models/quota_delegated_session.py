"""Trusted coordinator scope; PG still admits every individual physical attempt."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from typing import Any

from psycopg import sql

from .quota_delegated import DelegatedApproval, begin_delegated_batch, delegated_stage
from .quota_guard import QuotaGuard
from .quota_mode import current_delegated_session, delegated_session
from .quota_r16 import K31ConnectionApproval
from .quota_runtime import CallScope
from .quota_types import GuardConfigurationError, GuardRejected, identifier, instant


def require_active() -> DelegatedSession:
    session = current_delegated_session()
    if not isinstance(session, DelegatedSession):
        raise GuardRejected("manual_start_required")
    session.approval.check(session.guard.clock.now())
    return session


class DelegatedSession:
    def __init__(
        self,
        guard: QuotaGuard,
        approval: DelegatedApproval | K31ConnectionApproval,
        *,
        phase: str,
        scenario_ids: Sequence[str],
    ) -> None:
        approval.check(guard.clock.now())
        delegated_stage(approval, phase)
        if not scenario_ids or len(set(scenario_ids)) != len(scenario_ids):
            raise GuardConfigurationError("委托需要不同的计划场景")
        self.scenarios = tuple(identifier(value) for value in scenario_ids)
        self.guard, self.approval, self.phase = guard, approval, phase
        self._lock = threading.RLock()
        self._identity, self._sequence = uuid.uuid4().hex, 0
        self._receipt: dict[str, Any] | None = None

    @contextmanager
    def activate(self) -> Iterator[DelegatedSession]:
        self.approval.check(self.guard.clock.now())
        with delegated_session(self):
            yield self

    def scope(self, scenario_id: str) -> CallScope:
        if scenario_id not in self.scenarios:
            raise GuardRejected("batch_conflict")
        return CallScope(
            lane="probe" if self.phase in {"equivalence", "k31-connect"} else "eval",
            scenario_id=scenario_id,
        )

    def _state(self) -> tuple[int, int]:
        if self._receipt is None:
            return 0, 0
        with self.guard.store.connect() as connection:
            row = connection.execute(
                sql.SQL(
                    "SELECT count(*) AS n,count(*) FILTER(WHERE finished_at IS NULL) AS pending "
                    "FROM {} WHERE account_id=%s AND batch_id=%s"
                ).format(self.guard.store.table("core_model_usage")),
                (self.guard.store.account_id, self._receipt["batch_id"]),
            ).fetchone()
        return row["n"], row["pending"]

    def close(self) -> None:
        with self._lock:
            if self._receipt is not None:
                self.guard.finish_batch(self._receipt["batch_id"], self._receipt["authorization_id"])
                self._receipt = None

    def _prepare(self, scenario: str) -> dict[str, Any]:
        now = instant(self.guard.clock.now())
        self.approval.check(now)
        count, pending = self._state()
        if self._receipt is not None and (
            count >= 10
            or scenario not in self._receipt["scenario_ids"]
            or now >= datetime.fromisoformat(self._receipt["expires_at"])
        ):
            if pending:
                raise GuardRejected("in_flight_limit")
            self.close()
        if self._receipt is None:
            self._sequence += 1
            start = self.scenarios.index(scenario) // 10 * 10
            self._receipt = begin_delegated_batch(
                self.guard,
                self.approval,
                phase=self.phase,
                batch_id=f"v7-{self._identity}-{self._sequence}",
                scenario_ids=list(self.scenarios[start : start + 10]),
            )
        return self._receipt

    @contextmanager
    def permit_scope(self, scope: CallScope) -> Iterator[CallScope]:
        expected = "probe" if self.phase in {"equivalence", "k31-connect"} else "eval"
        if scope.lane != expected or scope.scenario_id not in self.scenarios:
            raise GuardRejected("batch_conflict")
        # Serialize local batch rollover across primary and judge; PG slots cover
        # other processes and retain unknown reservations after a coordinator crash.
        with self._lock:
            receipt = self._prepare(scope.scenario_id)
            yield replace(
                scope,
                batch_id=receipt["batch_id"],
                authorization_id=receipt["authorization_id"],
            )

    def snapshot(self) -> dict[str, Any]:
        state = self.guard.status()
        return {
            "candidate_commit": self.approval.candidate,
            "phase": self.phase,
            "batch_id": self._receipt["batch_id"] if self._receipt else None,
            "batch_requests": self._state()[0],
            "batches_started": self._sequence,
            "stop_kind": state["stop_kind"],
            "resume_at": state["resume_at"],
        }

"""Explicit v7 delegation identities; runtime never accepts a caller policy flag."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import sql

from .quota_gate import validate_gate
from .quota_types import GuardRejected, instant

PREFIX = "v7d-"
TOKEN = re.compile(r"v7d-([0-9a-f]{40})-(eq|core-k3|core-k3-256k)-[0-9a-f]{32}")
DEADLINE = datetime(2026, 10, 27, 14, tzinfo=UTC)
_SEAL = object()


@dataclass(frozen=True)
class DelegatedApproval:
    candidate: str
    expires_at: datetime
    equivalent: bool | None
    _seal: object = field(repr=False)

    def check(self, now: datetime) -> None:
        expected = (_SEAL, self.candidate, self.expires_at, self.equivalent)
        if self._seal != expected or instant(now) >= self.expires_at or self.expires_at > DEADLINE:
            raise GuardRejected("authorization_expired")


def approval_from_gate(value: Any, candidate: str, now: datetime) -> DelegatedApproval:
    """A trusted local CLI supplies a completed same-candidate scripted gate."""
    validate_gate(value, candidate)
    # A scripted report cannot attest that two real model identities are equal.
    # Core remains closed until a separate trusted equivalence verifier exists.
    if value.get("equivalent") is not None:
        raise GuardRejected("manual_start_required")
    approval = DelegatedApproval(candidate, DEADLINE, None, (_SEAL, candidate, DEADLINE, None))
    approval.check(now)
    return approval


def token_parts(value: Any) -> tuple[str, str] | None:
    match = TOKEN.fullmatch(value) if isinstance(value, str) else None
    return (match[1], match[2]) if match else None


def delegated_row(row: dict[str, Any] | None) -> bool:
    return row is not None and token_parts(row.get("authorization_id")) is not None


def begin_delegated_batch(
    guard: Any,
    approval: DelegatedApproval,
    *,
    phase: str,
    batch_id: str,
    scenario_ids: list[str],
) -> dict[str, Any]:
    from .quota_batches import _batch_digest, _begin_locked

    now = instant(guard.clock.now())
    approval.check(now)
    if phase not in {"equivalence", "core"} or phase == "core" and approval.equivalent is None:
        raise GuardRejected("manual_start_required")
    stage = "eq" if phase == "equivalence" else "core-k3-256k" if approval.equivalent else "core-k3"
    authorization = f"{PREFIX}{approval.candidate}-{stage}-" + uuid.uuid4().hex
    expires = min(now + timedelta(minutes=15), approval.expires_at)
    digest, expires = _batch_digest(batch_id, scenario_ids, authorization, expires, now)
    with guard.store.connect() as connection, connection.transaction():
        _begin_locked(
            connection,
            guard.store,
            now,
            batch_id,
            scenario_ids,
            authorization,
            expires,
            digest,
            delegated=True,
        )
    return {
        "schema": "member-delegated-start-v7",
        "candidate_commit": approval.candidate,
        "phase": phase,
        "batch_id": batch_id,
        "authorization_id": authorization,
        "scenario_ids": list(scenario_ids),
        "expires_at": expires.isoformat(),
        "delegation_expires_at": approval.expires_at.isoformat(),
        "model_calls": 0,
    }


def check_delegated_attempt(connection: Any, store: Any, row: dict[str, Any], data: dict[str, Any]) -> None:
    candidate, phase = token_parts(row["authorization_id"])
    models = {"k3", "k3-256k"} if phase == "eq" else {phase.removeprefix("core-")}
    if (
        data["provider"] != "kimi_code"
        or data["model"] not in models
        or data["role"] not in {"primary", "critic", "evaluation"}
    ):
        raise GuardRejected("batch_conflict")
    if phase == "eq":
        count = connection.execute(
            sql.SQL(
                "SELECT count(*) AS n FROM {} u JOIN {} b USING(account_id,batch_id) "
                "WHERE u.account_id=%s AND b.authorization_id LIKE %s"
            ).format(store.table("core_model_usage"), store.table("core_model_batches")),
            (store.account_id, f"{PREFIX}{candidate}-eq-%"),
        ).fetchone()["n"]
        if count >= 20:
            raise GuardRejected("delegation_request_limit")


def resume_delegated(guard: Any, approval: DelegatedApproval) -> bool:
    now = instant(guard.clock.now())
    approval.check(now)
    with guard.store.connect() as connection, connection.transaction():
        account = guard.store.locked(connection, now, stopped=True)
        if account["stop_kind"] is None:
            return False
        if account["stop_kind"] != "quota_5h" or account["resume_at"] is None or now < account["resume_at"]:
            raise GuardRejected(account["stop_kind"], account["resume_at"])
        authorization = "delegated-resume-v7-" + uuid.uuid4().hex
        guard.store.control_action(connection, authorization, "clear_stop", None, now)
        connection.execute(
            sql.SQL(
                "UPDATE {} SET stop_kind=NULL,stopped_at=NULL,resume_at=NULL,clear_authorization=%s WHERE account_id=%s"
            ).format(guard.store.table("core_model_accounts")),
            (authorization, guard.store.account_id),
        )
        return True

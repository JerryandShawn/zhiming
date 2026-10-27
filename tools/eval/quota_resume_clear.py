"""Consume one live eligibility to clear exactly its terminal quota stop; never execute."""

from __future__ import annotations

from mingjing_core.models.quota_r16 import core_token_stage

import uuid
from dataclasses import dataclass
from typing import Any

from psycopg import sql

from mingjing_core.models.quota_delegated import token_parts
from mingjing_core.models.quota_types import instant
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota_resume_evidence import _stop, gather, require
from tools.eval.quota_resume_witness import (
    _check_consumed,
    _consume_for_clear,
    _finish_clear,
)


@dataclass(frozen=True)
class QuotaClearReceipt:
    schema: str
    run_id: str
    epoch: int
    seq: int
    terminal_id: str
    terminal_sha256: str
    evidence_sha256: str
    authorization_sha256: str
    audit_sha256: str
    cleared_at: str
    execution_authority: bool = False
    central_stop_cleared: bool = True
    model_calls: int = 0


class _ResumeHandoff:
    __slots__ = ()

    def __new__(cls):
        raise LifecycleError("QUOTA_RESUME_PRIVATE_HANDOFF_REQUIRED")

    def __reduce__(self):
        raise LifecycleError("QUOTA_RESUME_HANDOFF_NOT_SERIALIZABLE")


@dataclass(repr=False)
class _HandoffState:
    handoff: _ResumeHandoff
    entry: Any
    account: dict
    receipt: QuotaClearReceipt
    logical: dict
    claimed: dict | None = None
    consumed: bool = False


_HANDOFFS: dict[int, _HandoffState] = {}


def _peek_handoff(handoff):
    require(type(handoff) is _ResumeHandoff)
    state = _HANDOFFS.get(id(handoff))
    require(state is not None and state.handoff is handoff and not state.consumed)
    _check_consumed(state.entry)
    return state


def _bind_claim(handoff, run):
    state = _peek_handoff(handoff)
    require(
        state.claimed is None
        and run["id"] == state.entry.evidence.run_id
        and run["lease_token"]
    )
    state.claimed = dict(run)


def _consume_handoff(handoff, repo, run):
    state = _peek_handoff(handoff)
    require(state.entry.repo is repo and state.claimed == run)
    state.consumed = True
    return state.entry, state.logical


def _slots(connection: Any, guard: Any) -> None:
    for slot in (0, 1):
        require(
            connection.execute(
                "SELECT pg_try_advisory_lock(%s) AS held", (guard._key(slot),)
            ).fetchone()["held"]
        )


def _quiescent(connection: Any, store: Any) -> None:
    for name, condition in (
        ("core_model_usage", "finished_at IS NULL OR status IN ('reserved','unknown')"),
        ("core_model_batches", "status='active'"),
    ):
        row = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE account_id=%s AND (").format(
                store.table(name)
            )
            + sql.SQL(condition)
            + sql.SQL(") LIMIT 1"),
            (store.account_id,),
        ).fetchone()
        require(row is None)


def _grant(connection, store, batch, entry, usage) -> None:
    scenarios = batch["scenario_ids"]
    require(
        type(scenarios) is list
        and 1 <= len(scenarios) <= 10
        and len(set(scenarios)) == len(scenarios)
    )
    require(
        entry.binding.scenario_id in scenarios
        and set(scenarios) <= set(entry.session.scenarios)
        and batch["fingerprint"] == fingerprint(scenarios)
        and batch["status"] == "completed"
        and batch["finished_at"] is not None
        and batch["recovery_authorization"] is None
        and batch["finished_at"] >= batch["started_at"]
        and token_parts(batch["authorization_id"])
        == (entry.binding.candidate_commit, core_token_stage(entry.binding.model))
    )
    grant = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE account_id=%s AND authorization_id=%s").format(
            store.table("core_model_authorizations")
        ),
        (store.account_id, batch["authorization_id"]),
    ).fetchone()
    require(
        grant is not None
        and grant["kind"] == "batch"
        and grant["batch_id"] == batch["batch_id"]
        and grant["created_at"] == batch["started_at"]
        and batch["expires_at"] <= grant["expires_at"]
        and grant["created_at"]
        < grant["expires_at"]
        <= entry.session.approval.expires_at
    )
    for row in usage:
        if row["batch_id"] == batch["batch_id"]:
            require(
                batch["started_at"] <= row["at"] < grant["expires_at"]
                and row["at"] <= batch["expires_at"]
            )
            require(row["scenario_id"] in scenarios)
            require(
                row["finished_at"] is not None
                and row["at"] <= row["finished_at"] <= batch["finished_at"]
            )


def _central(connection, entry) -> dict:
    store, evidence = entry.guard.store, entry.evidence
    account = store.verify(connection, lock=True)
    usage = connection.execute(
        sql.SQL(
            "SELECT * FROM {} WHERE account_id=%s AND run_id=%s ORDER BY id"
        ).format(store.table("core_model_usage")),
        (store.account_id, evidence.run_id),
    ).fetchall()
    rows = connection.execute(
        sql.SQL(
            "SELECT * FROM {} WHERE account_id=%s AND batch_id=ANY(%s) ORDER BY batch_id"
        ).format(store.table("core_model_batches")),
        (store.account_id, sorted({row["batch_id"] for row in usage})),
    ).fetchall()
    batches = {row["batch_id"]: row for row in rows}
    require(
        fingerprint(usage) == evidence.usage_sha256
        and fingerprint(batches) == evidence.batches_sha256
    )
    terminal = next(
        (row for row in usage if row["attempt_id"] == evidence.terminal_id), None
    )
    require(terminal is not None and fingerprint(terminal) == evidence.terminal_sha256)
    require(terminal["status"] == "quota_5h" and terminal["finished_at"] is not None)
    require(fingerprint(_stop(account, terminal, entry.guard)) == evidence.stop_sha256)
    _quiescent(connection, store)
    for batch in rows:
        _grant(connection, store, batch, entry, usage)
    return account


def _write(connection, entry, account, now):
    store, evidence = entry.guard.store, entry.evidence
    authorization = "eval-exact-quota-clear-" + uuid.uuid4().hex
    require(store.control_action(connection, authorization, "clear_stop", None, now))
    after = connection.execute(
        sql.SQL(
            "UPDATE {} SET stop_kind=NULL,stopped_at=NULL,resume_at=NULL,clear_authorization=%s,last_clock_at=%s "
            "WHERE account_id=%s AND ledger_identity=%s AND location_id=%s AND stop_kind='quota_5h' "
            "AND stopped_at=%s AND resume_at=%s AND clear_authorization IS NOT DISTINCT FROM %s "
            "AND last_clock_at IS NOT DISTINCT FROM %s RETURNING *"
        ).format(store.table("core_model_accounts")),
        (
            authorization,
            now,
            store.account_id,
            account["ledger_identity"],
            account["location_id"],
            account["stopped_at"],
            account["resume_at"],
            account["clear_authorization"],
            account["last_clock_at"],
        ),
    ).fetchone()
    require(after is not None)
    grant = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE account_id=%s AND authorization_id=%s").format(
            store.table("core_model_authorizations")
        ),
        (store.account_id, authorization),
    ).fetchone()
    require(
        grant is not None
        and grant["kind"] == "clear_stop"
        and grant["batch_id"] is None
    )
    require(grant["created_at"] == grant["expires_at"] == now)
    audit = fingerprint([evidence.sha256, evidence.stop_sha256, grant, after])
    return QuotaClearReceipt(
        "quota-exact-clear-v1",
        evidence.run_id,
        evidence.epoch,
        evidence.seq,
        evidence.terminal_id,
        evidence.terminal_sha256,
        evidence.sha256,
        fingerprint(authorization),
        audit,
        now.isoformat(),
    )


def _commit_clear(entry):
    guard, target, control, binding = (
        entry.guard,
        entry.target,
        entry.control,
        entry.binding,
    )
    try:
        _check_consumed(entry)
        require(entry.session._receipt is None)
        with guard.store.connect() as connection:
            _slots(connection, guard)
            with connection.transaction():
                now = instant(guard.clock.now())
                entry.session.approval.check(now)
                account = _central(connection, entry)
                logical_id = f"{entry.evidence.run_id}:e{entry.evidence.epoch}:agent_model_attempts:{entry.evidence.seq}"
                logical = entry.repo.get(target.owner, "runtime_step", logical_id)
                require(gather(target, control, binding, guard) == entry.evidence)
                require(
                    fingerprint(logical)
                    == fingerprint(
                        entry.repo.get(target.owner, "runtime_step", logical_id)
                    )
                )
                _check_consumed(entry)
                now = instant(guard.clock.now())
                entry.session.approval.check(now)
                require(
                    account["last_clock_at"] is None or now >= account["last_clock_at"]
                )
                require(
                    account["resume_at"] is not None and now >= account["resume_at"]
                )
                receipt = _write(connection, entry, account, now)
        return receipt, account, logical
    except Exception:
        raise LifecycleError("QUOTA_EXACT_CLEAR_FAILED_OR_UNKNOWN") from None


def clear_quota5h(witness, *, target, control, binding, guard) -> QuotaClearReceipt:
    """Only this explicit transition writes; failure/unknown commit never restores its witness."""
    entry = _consume_for_clear(
        witness, target=target, control=control, binding=binding, guard=guard
    )
    try:
        with entry.session._lock:
            receipt, _, _ = _commit_clear(entry)
        return receipt
    finally:
        _finish_clear(entry)


def _resume_after_clear(witness, *, target, control, binding, guard, continuation):
    """Private same-stack continuation, issued only after confirmed COMMIT and slot connection close."""
    entry = _consume_for_clear(
        witness, target=target, control=control, binding=binding, guard=guard
    )
    handoff = object.__new__(_ResumeHandoff)
    try:
        with entry.session._lock:
            receipt, account, logical = _commit_clear(entry)
            _HANDOFFS[id(handoff)] = _HandoffState(
                handoff, entry, account, receipt, logical
            )
            return continuation(handoff)
    finally:
        _HANDOFFS.pop(id(handoff), None)
        _finish_clear(entry)

"""Exact stop transition with native closed grants; HTTP alone is mocked."""

from __future__ import annotations

import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import asdict
from datetime import timedelta

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.transaction import Transaction

from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.models import quota_delegated
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota_resume_clear import clear_quota5h
from tools.eval.quota_resume_witness import QuotaResumeWitness, check, eligible_quota5h

from .test_eval_quota_resume_eligibility_pg import arguments, observed
from .test_eval_quota_resume_eligibility_pg import pending as shared_pending


@pytest.fixture
def pending(p2_repo, monkeypatch, request):
    with contextmanager(shared_pending.__wrapped__)(p2_repo, monkeypatch, request) as value:
        value.live.session.close()  # Real finish_batch before mint/baseline; the transition never closes it.
        assert value.live.session._receipt is None
        with value.live.guard.store.connect() as connection:
            batch = connection.execute(
                sql.SQL("SELECT * FROM {} WHERE account_id=%s").format(
                    value.live.guard.store.table("core_model_batches")
                ),
                (value.live.guard.store.account_id,),
            ).fetchone()
        assert batch["status"] == "completed" and batch["finished_at"] is not None
        assert batch["recovery_authorization"] is None
        yield value


def central(value):
    guard = value.live.guard
    with guard.store.connect() as connection:
        account = guard.store.verify(connection)
        rows = [
            connection.execute(
                sql.SQL('SELECT to_jsonb(t) AS row FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                    guard.store.table(name)
                )
            ).fetchall()
            for name in ("core_model_usage", "core_model_batches", "core_model_authorizations")
        ]
    return account, rows


def stable(value):
    target = value.target
    hashes = []
    for name in (
        "core_owners",
        "core_subjects",
        "core_versions",
        "core_entities",
        "core_runs",
        "core_run_steps",
        "core_run_events",
        "core_mutation_requests",
        "core_operations",
        "core_revocations",
    ):
        with target.repo.transaction() as connection:
            rows = connection.execute(
                sql.SQL('SELECT to_jsonb(t) AS row FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                    target.repo.table(name)
                )
            ).fetchall()
        hashes.append(fingerprint(rows))
    with value.saved.control.connect() as connection:
        hashes.append(
            fingerprint(connection.execute(sql.SQL("SELECT * FROM {}").format(value.saved.control.table())).fetchall())
        )
    return hashes, len(value.live.sent)


def forbid_execution(monkeypatch):
    def rejected(*args, **kwargs):
        pytest.fail("EXACT_CLEAR_MUST_NOT_CLAIM_EXECUTE_GENERIC_RESUME_OR_POST")

    for cls, name in (
        (PostgresRepository, "claim_run"),
        (AgentRuntime, "execute"),
        (QuotaGuard, "acquire"),
        (QuotaGuard, "clear_stop"),
        (httpx.Client, "send"),
    ):
        monkeypatch.setattr(cls, name, rejected)
    monkeypatch.setattr(quota_delegated, "resume_delegated", rejected)


def assert_central_clear(value, before):
    prior, old = before
    account, current = central(value)
    assert current[:2] == old[:2]  # Entire original usage and batches, including expired grant windows.
    old_grants = {row["row"]["authorization_id"]: row for row in old[2]}
    grants = {row["row"]["authorization_id"]: row for row in current[2]}
    assert {key: grants[key] for key in old_grants} == old_grants and len(grants) == len(old_grants) + 1
    added = grants[account["clear_authorization"]]["row"]
    assert added["kind"] == "clear_stop" and added["batch_id"] is None
    assert added["created_at"] == added["expires_at"]
    assert account["stop_kind"] is account["stopped_at"] is account["resume_at"] is None
    assert account["last_clock_at"] >= prior["last_clock_at"]
    changed = {"stop_kind", "stopped_at", "resume_at", "clear_authorization", "last_clock_at"}
    assert {k: v for k, v in account.items() if k not in changed} == {
        k: v for k, v in prior.items() if k not in changed
    }
    return account


def reject_other_session(value, args):
    other = DelegatedSession(
        value.live.guard, value.live.session.approval, phase="core", scenario_ids=[value.saved.binding.scenario_id]
    )
    with ExitStack() as eligible:
        with value.live.session.activate():
            rejected = eligible.enter_context(eligible_quota5h(**args))
        with other.activate(), pytest.raises(LifecycleError):
            clear_quota5h(rejected, **args)


def test_native_closed_batch_clears_exactly_once_without_executing(pending, monkeypatch):
    value, args = pending, arguments(pending)
    before, frozen = central(value), stable(value)
    forbid_execution(monkeypatch)
    for forged in ({"eligible": True}, object.__new__(QuotaResumeWitness)):
        with pytest.raises(LifecycleError):
            clear_quota5h(forged, **args)
    with value.live.session.activate():
        with eligible_quota5h(**args) as exited:
            pass
        with pytest.raises(LifecycleError):
            clear_quota5h(exited, **args)
    reject_other_session(value, args)
    assert central(value) == before and stable(value) == frozen
    with value.live.session.activate(), eligible_quota5h(**args) as witness:
        receipt = clear_quota5h(witness, **args)
        assert not receipt.execution_authority and receipt.central_stop_cleared and receipt.model_calls == 0
        assert len(receipt.audit_sha256) == 64 and receipt.terminal_id.startswith("http-")
        with pytest.raises(LifecycleError):
            clear_quota5h(witness, **args)
        with pytest.raises(LifecycleError):
            check(witness, **args)
        with pytest.raises(LifecycleError):
            value.target.send({"user": "attached send must stay closed", "_index": 1})
    account = assert_central_clear(value, before)
    assert receipt.authorization_sha256 == fingerprint(account["clear_authorization"])
    assert all("面试" not in str(item) for item in asdict(receipt).values())
    assert stable(value) == frozen


@pytest.mark.parametrize("change", ["stop", "terminal", "source"])
def test_stop_terminal_or_cross_database_source_drift_burns_without_writes(pending, monkeypatch, change):
    value, args = pending, arguments(pending)
    with value.live.session.activate(), eligible_quota5h(**args) as witness:
        if change == "stop":
            value.live.guard.record_stop("access_terminated")
        elif change == "source":
            target = value.target
            source = target.repo.get(target.owner, "message", target.bindings["turn-1"])
            target.repo.update(
                target.owner, "message", source["id"], {"content": "合成原话漂移"}, expected_revision=source["revision"]
            )
        else:
            store = value.live.guard.store
            with store.connect() as connection, connection.transaction():
                connection.execute(
                    sql.SQL(
                        "UPDATE {} SET latency_ms=coalesce(latency_ms,0)+1 WHERE account_id=%s AND status='quota_5h'"
                    ).format(store.table("core_model_usage")),
                    (store.account_id,),
                )
        before, frozen = observed(value), stable(value)
        forbid_execution(monkeypatch)
        with pytest.raises(LifecycleError):
            clear_quota5h(witness, **args)
        with pytest.raises(LifecycleError):
            clear_quota5h(witness, **args)
        assert observed(value) == before and stable(value) == frozen


def contaminate(value, kind):
    store, now = value.live.guard.store, value.live.guard.clock.now()
    with store.connect() as connection, connection.transaction():
        if kind == "active_batch":
            batch, authorization = "other-" + uuid.uuid4().hex, "other-auth-" + uuid.uuid4().hex
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(account_id,batch_id,scenario_ids,fingerprint,authorization_id,"
                    "expires_at,status,started_at) VALUES(%s,%s,%s,%s,%s,%s,'active',%s)"
                ).format(store.table("core_model_batches")),
                (
                    store.account_id,
                    batch,
                    ["M01"],
                    fingerprint(["M01"]),
                    authorization,
                    now + timedelta(minutes=5),
                    now,
                ),
            )
        else:
            connection.execute(
                sql.SQL(
                    "INSERT INTO {}(account_id,attempt_id,at,provider,model,role,lane,bucket,run_id,"
                    "status,finished_at) "
                    "VALUES(%s,%s,%s,'synthetic','k3-256k','primary','interactive','interactive','another-run',%s,%s)"
                ).format(store.table("core_model_usage")),
                (
                    store.account_id,
                    "http-" + uuid.uuid4().hex,
                    now - timedelta(hours=7),
                    kind,
                    now if kind == "unknown" else None,
                ),
            )


@pytest.mark.parametrize("kind", ["reserved", "unknown", "active_batch", "slot"])
def test_all_account_unknown_work_or_real_held_slot_prevents_clear(pending, monkeypatch, kind):
    value, args, store = pending, arguments(pending), pending.live.guard.store
    if kind != "slot":
        contaminate(value, kind)  # Deliberately invalid self-owned PG state is only a rejection fixture.
    with store.connect() as held:
        if kind == "slot":
            assert held.execute("SELECT pg_try_advisory_lock(%s) AS held", (value.live.guard._key(1),)).fetchone()[
                "held"
            ]
        with value.live.session.activate(), eligible_quota5h(**args) as witness:
            before, frozen = observed(value), stable(value)
            forbid_execution(monkeypatch)
            with pytest.raises(LifecycleError):
                clear_quota5h(witness, **args)
            with pytest.raises(LifecycleError):
                clear_quota5h(witness, **args)
            assert observed(value) == before and stable(value) == frozen
            if kind == "slot":
                assert held.execute("SELECT pg_try_advisory_lock(%s) AS held", (value.live.guard._key(0),)).fetchone()[
                    "held"
                ]


def inject_native_fault(monkeypatch, value, kind):
    execute, exiting = psycopg.Connection.execute, Transaction.__exit__
    seen = dict(updates=0, commits=0, grant_visible=False, connection=None)
    store = value.live.guard.store

    def altered(connection, query, params=None, **kwargs):
        text = query.as_string(connection) if isinstance(query, sql.Composable) else query
        if (
            type(text) is str
            and "SET stop_kind=NULL,stopped_at=NULL,resume_at=NULL,clear_authorization=" in text
            and "last_clock_at=" in text
        ):
            seen["updates"] += 1
            seen["connection"] = connection
            found = execute(
                connection,
                sql.SQL("SELECT count(*) AS n FROM {} WHERE account_id=%s AND kind='clear_stop'").format(
                    store.table("core_model_authorizations")
                ),
                (store.account_id,),
            ).fetchone()
            seen["grant_visible"] = found["n"] == 1
            if kind == "rollback":
                return execute(connection, "SELECT 1/0")  # Native PG failure after the actual authorization INSERT.
        return execute(connection, query, params, **kwargs)

    def uncertain(transaction, exc_type, exc_value, traceback):
        result = exiting(transaction, exc_type, exc_value, traceback)
        if kind == "commit_unknown" and transaction._conn is seen["connection"] and exc_type is None:
            seen["commits"] += 1
            raise psycopg.OperationalError("SYNTHETIC_ACK_LOST_AFTER_NATIVE_COMMIT")
        return result

    monkeypatch.setattr(psycopg.Connection, "execute", altered)
    monkeypatch.setattr(Transaction, "__exit__", uncertain)
    return seen


@pytest.mark.parametrize("kind", ["rollback", "commit_unknown"])
def test_native_sql_rollback_or_commit_unknown_never_reuses_witness(pending, monkeypatch, kind):
    value, args = pending, arguments(pending)
    before, frozen, full = central(value), stable(value), observed(value)
    forbid_execution(monkeypatch)
    with value.live.session.activate(), eligible_quota5h(**args) as witness:
        seen = inject_native_fault(monkeypatch, value, kind)
        with pytest.raises(LifecycleError):
            clear_quota5h(witness, **args)
        assert seen["updates"] == 1 and seen["grant_visible"]
        with pytest.raises(LifecycleError):
            clear_quota5h(witness, **args)
        assert seen["updates"] == 1 and stable(value) == frozen
        if kind == "rollback":
            assert seen["commits"] == 0 and observed(value) == full
        else:
            assert seen["commits"] == 1
            assert_central_clear(value, before)  # Observe reality; no compensating stop/retry is performed.

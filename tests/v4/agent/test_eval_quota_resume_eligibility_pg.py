"""Real quota response/checkpoint evidence; only the provider transport is replaced."""

from __future__ import annotations

import copy
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest
from psycopg import sql

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota_resume_witness import QuotaResumeWitness, check, eligible_quota5h

from .test_eval_lifecycle_pg import saved as shared_saved
from .test_eval_v4_live_pg import live as shared_live


@pytest.fixture
def pending(p2_repo, monkeypatch, request):
    mode = getattr(request, "param", "due")
    with contextmanager(shared_live.__wrapped__)(p2_repo, monkeypatch) as live:
        original = live.handle

        def respond(message):
            response = original(message)
            if mode == "missing_reset" and response.status_code == 403:
                response.headers.pop("Retry-After", None)
            return response

        live.handle = respond
        with contextmanager(shared_saved.__wrapped__)(live, monkeypatch) as saved:
            saved.target.detach()
            target = saved.new()
            target.attach(saved.control, saved.session, saved.binding, live.guard)
            with live.guard.store.connect() as connection:
                account = live.guard.store.verify(connection)
            assert account["stop_kind"] == "quota_5h" and len(live.sent) == 2
            if mode not in {"early", "missing_reset"}:
                assert account["resume_at"] is not None
                live.guard.clock = FrozenClock(account["resume_at"])
            yield SimpleNamespace(saved=saved, target=target, live=live, mode=mode)


def arguments(value):
    return dict(target=value.target, control=value.saved.control, binding=value.saved.binding, guard=value.live.guard)


def observed(value):
    target, guard, control = value.target, value.live.guard, value.saved.control
    names = [
        (target.repo, name)
        for name in ("core_runs", "core_run_steps", "core_run_events", "core_entities", "core_mutation_requests")
    ] + [
        (guard.store, name)
        for name in ("core_model_accounts", "core_model_usage", "core_model_batches", "core_model_authorizations")
    ]
    result = []
    for store, name in names:
        with guard.store.connect() as connection:
            rows = connection.execute(
                sql.SQL('SELECT to_jsonb(t) AS row FROM {} t ORDER BY to_jsonb(t)::text COLLATE "C"').format(
                    store.table(name)
                )
            ).fetchall()
        result.append(fingerprint(rows))
    with control.connect() as connection:
        result.append(fingerprint(connection.execute(sql.SQL("SELECT * FROM {}").format(control.table())).fetchall()))
    return result, len(value.live.sent)


def forbid_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("PRECLEAR_ELIGIBILITY_MUST_NOT_WRITE_EXECUTE_OR_POST")

    for cls, name in (
        (QuotaGuard, "acquire"),
        (QuotaGuard, "clear_stop"),
        (PostgresRepository, "claim_run"),
        (httpx.Client, "send"),
    ):
        monkeypatch.setattr(cls, name, forbidden)


def test_due_native_quota_and_closed_budget_mint_only_live_readonly_eligibility(pending, monkeypatch):
    value, args = pending, arguments(pending)
    before = observed(value)
    forbid_effects(monkeypatch)
    with value.live.session.activate():
        with eligible_quota5h(**args) as witness:
            summary = check(witness, **args)
            run = value.target.repo.fetch_run(value.target.owner, summary.run_id)
            assert (summary.run_id, summary.epoch, summary.turn) == (value.target.run_ids[-1], run["retry_epoch"], 1)
            assert not summary.execution_authority and not summary.central_stop_cleared and summary.model_calls == 0
            assert summary.consumed_ns > 0 and len(summary.evidence_sha256) == 64
            assert observed(value) == before
            with pytest.raises(LifecycleError):
                copy.copy(witness)
            with pytest.raises(LifecycleError):
                value.target.send({"user": "must stay closed", "_index": 1})
        with pytest.raises(LifecycleError):
            check(witness, **args)
    assert observed(value) == before


@pytest.mark.parametrize("pending", ["early", "missing_reset", "access", "unknown", "missing"], indirect=True)
def test_nonrecoverable_real_stop_or_physical_evidence_never_mints(pending, monkeypatch):
    value, guard = pending, pending.live.guard
    if value.mode == "access":
        guard.record_stop("access_terminated")
    elif value.mode in {"unknown", "missing"}:
        with guard.store.connect() as connection, connection.transaction():
            last = connection.execute(
                sql.SQL("SELECT attempt_id FROM {} WHERE account_id=%s AND status='quota_5h'").format(
                    guard.store.table("core_model_usage")
                ),
                (guard.store.account_id,),
            ).fetchone()
            assert last
            statement = (
                "DELETE FROM {} WHERE attempt_id=%s"
                if value.mode == "missing"
                else "UPDATE {} SET status='unknown' WHERE attempt_id=%s"
            )
            connection.execute(sql.SQL(statement).format(guard.store.table("core_model_usage")), (last["attempt_id"],))
    before = observed(value)
    forbid_effects(monkeypatch)
    with value.live.session.activate(), pytest.raises(LifecycleError), eligible_quota5h(**arguments(value)):
        pytest.fail("ineligible evidence cannot yield a witness")
    assert observed(value) == before


@pytest.mark.parametrize("change", ["control", "source", "budget"])
def test_current_pg_drift_and_unregistered_objects_reject_original_witness(pending, monkeypatch, change):
    value, args = pending, arguments(pending)
    forbid_effects(monkeypatch)
    with value.live.session.activate(), eligible_quota5h(**args) as witness:
        for fake in ({"eligible": True}, object.__new__(QuotaResumeWitness)):
            with pytest.raises(LifecycleError):
                check(fake, **args)
        with pytest.raises(LifecycleError):
            QuotaResumeWitness()
        saved, target = value.saved, value.target
        if change == "control":
            row = saved.control.load(saved.session, saved.binding, value.live.guard)
            saved.control.save(
                saved.session,
                saved.binding,
                value.live.guard,
                **{key: row[key] for key in ("target_schema", "target_location", "state_id", "state_sha256")},
            )
        elif change == "source":
            run = target.repo.fetch_run(target.owner, target.run_ids[-1])
            source = target.repo.get(target.owner, "message", run["request"]["source_message_id"])
            target.repo.update(
                target.owner,
                "message",
                source["id"],
                {"content": "synthetic changed source"},
                expected_revision=source["revision"],
            )
        else:
            row = next(
                row
                for row in target.repo.list(target.owner, "runtime_step")
                if row.get("stage") == "eval_execution_budget"
            )
            budget = copy.deepcopy(row["budget"])
            budget["segments"][-1]["elapsed_ns"] += 1
            target.repo.update(
                target.owner, "runtime_step", row["id"], {"budget": budget}, expected_revision=row["revision"]
            )
        before = observed(value)
        with pytest.raises(LifecycleError):
            check(witness, **args)
        assert observed(value) == before

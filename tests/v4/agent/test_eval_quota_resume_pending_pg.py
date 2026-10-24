"""Same-run quota recovery uses real case effects, PG leases, budgets and Journal."""

from __future__ import annotations

import copy
import uuid
from contextlib import closing, contextmanager
from datetime import timedelta
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from models.test_quota_http_pg import rows as quota_rows
from psycopg import sql

from mingjing_core.application import agent_model_history_evidence
from mingjing_core.application.agent_case_effect_marker import SCHEMA as CASE_EFFECT
from mingjing_core.application.agent_pending_effects import _initial
from mingjing_core.application.agent_regeneration import AgentRegenerator
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.models.quota_attempt_observer import ModelAttemptUnconfirmed
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.quota_resume_witness import eligible_quota5h
from tools.eval.targets.v4_durable import DurableCore30Target
from tools.eval.targets.v4_execution_budget_store import BudgetStore
from tools.eval.targets.v4_lifecycle_state import read_private

from . import model_attempt_support
from .test_eval_quota_clear_pg import central
from .test_eval_quota_history_evidence_pg import history as shared_history
from .test_eval_quota_resume_pending_support import assert_clear_without_post_or_new_epoch, core_state, rows
from .test_eval_v4_live_pg import wire


def steps(value):
    return sorted(
        (row for row in rows(value, "core_run_steps") if row["run_id"] == value.run["id"]),
        key=lambda row: row["seq"],
    )


def budget(value):
    return value.target.repo.get(
        value.target.owner, "runtime_step", BudgetStore.ident(value.run["id"], value.run["retry_epoch"])
    )["budget"]


def attempts(value):
    return {
        row["value"]["seq"]: row
        for row in value.target.repo.list(value.target.owner, "runtime_step")
        if row.get("stage") == "agent_model_attempts" and row.get("run_id") == value.run["id"]
    }


def preserved(value):
    target = value.target
    private = [
        row
        for row in target.repo.list(target.owner, "runtime_step", include_deleted=True)
        if row.get("run_id") == value.run["id"]
        and (
            row.get("stage") in {"agent_initial_context", "agent_model_request"}
            or row.get("schema") == CASE_EFFECT
            or row.get("stage") == "agent_model_attempts"
            and row["value"]["seq"] < value.pending_seq
        )
    ]
    return {
        "case": target.repo.get(target.owner, "case", value.case["id"]),
        "private": sorted(private, key=lambda row: row["id"]),
        "steps": [row for row in steps(value) if row["seq"] < value.pending_seq],
        "events": [
            row for row in rows(value, "core_run_events") if row["kind"] in {"started", "tool_call", "tool_result"}
        ],
        "mutations": [row for row in rows(value, "core_mutation_requests") if row["operation"] == "agent_case_update"],
        "operations": [
            row
            for row in rows(value, "core_operations")
            if row["operation_id"]
            in {f"run:{value.run['id']}:e{value.run['retry_epoch']}:s{seq}:case" for seq in (2, 4)}
        ],
    }


def attach(history, control, binding):
    old, live = history.observed.target, history.observed.live
    session = old.checkpoint(control, binding, live.guard, turn=1)
    old.detach()
    target = DurableCore30Target(
        model=binding.model, dsn=old.dsn, environment=live.environment, adapter_factory=live.factory
    )
    live.targets.append(target)
    target.attach(control, session, binding, live.guard)
    return target, session


def assert_real_effects(value):
    effects = [row for row in value.original["private"] if row.get("schema") == CASE_EFFECT]
    native = [row for row in value.original["steps"] if row["kind"] == "tool"]
    expected = [
        {"write_status": "saved", "kind": "case", "id": value.case["id"], "revision": value.case["revision"] + offset}
        for offset in (1, 2)
    ]
    assert len(effects) == len(value.original["mutations"]) == len(value.original["operations"]) == 2
    assert [row["seq"] for row in native] == [2, 4]
    assert [row["output"]["receipt"] for row in native] == expected
    assert [row["output"]["receipt"] for row in sorted(effects, key=lambda row: row["seq"])] == expected
    assert {row["request_key"] for row in value.original["mutations"]} == {
        f"run:{value.run['id']}:e{value.run['retry_epoch']}:s{seq}" for seq in (2, 4)
    }
    assert {fingerprint(row["receipt"]) for row in value.original["mutations"]} == {
        fingerprint(row) for row in expected
    }
    assert value.original["case"]["revision"] == value.case["revision"] + 2


@pytest.fixture
def pending(p2_repo, monkeypatch, request):
    monkeypatch.setattr(model_attempt_support, "Core30LiveTarget", DurableCore30Target)
    with contextmanager(shared_history.__wrapped__)(p2_repo, monkeypatch, request) as history:
        old, live = history.observed.target, history.observed.live
        assert isinstance(old, DurableCore30Target) and old._budget_started
        live.session.close()
        assert live.session._receipt is None
        control = LifecycleControl(live.guard.store.dsn, "eval_control_" + uuid.uuid4().hex)
        control.initialize(live.guard)
        binding = LifecycleBinding.capture(live.guard, "a" * 40, history.observed.case, old.model)
        try:
            target, session = attach(history, control, binding)
            with live.guard.store.connect() as connection:
                account = live.guard.store.verify(connection)
            assert account["stop_kind"] == "quota_5h" and account["resume_at"] is not None
            live.guard.clock = FrozenClock(account["resume_at"])
            value = SimpleNamespace(
                target=target,
                live=live,
                control=control,
                binding=binding,
                session=session,
                run=history.run,
                case=history.case,
                pending_seq=5,
            )
            value.original = preserved(value)
            assert_real_effects(value)
            value.old_usage = quota_rows(live.guard)
            value.old_attempts = copy.deepcopy(attempts(value)[5]["value"]["attempts"])
            value.old_budget = copy.deepcopy(budget(value))
            value.old_record = control.load(session, binding, live.guard)
            value.old_pin = copy.deepcopy(history.run["usage"]["agent_runtime"]["limit_epochs"])
            assert len(value.old_budget["segments"]) == 1 and value.old_budget["segments"][0]["phase"] == "closed"
            assert [row["seq"] for row in steps(value)] == [1, 2, 3, 4, 5]
            assert steps(value)[-1]["status"] == "started" and len(live.sent) == 3
            alias = next(
                key
                for row in value.original["private"]
                if row.get("stage") == "agent_initial_context"
                for key, item in row["output"]["alias_map"].items()
                if item["kind"] == "case" and item["id"] == history.case["id"]
            )
            value.answer = "两次更新已完成，下一步可以复盘。〔" + alias + "〕"
            yield value
        finally:
            with psycopg.connect(live.guard.store.dsn, autocommit=True) as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(control.schema)))


def arguments(value):
    return dict(target=value.target, control=value.control, binding=value.binding, guard=value.live.guard)


def resume(value):
    with eligible_quota5h(**arguments(value)) as witness:
        return value.target.resume_pending(
            witness, control=value.control, binding=value.binding, guard=value.live.guard
        )


def assert_single_attempt_and_preserved_prefix(value, kind):
    target, live = value.target, value.live
    run = target.repo.fetch_run(target.owner, value.run["id"])
    assert target.run_ids == [value.run["id"]] and len(rows(value, "core_runs")) == 1
    assert run["retry_epoch"] == value.run["retry_epoch"] and run["request"] == value.run["request"]
    assert run["usage"]["agent_runtime"]["limit_epochs"] == value.old_pin
    assert run["deadline_at"] == value.run["deadline_at"] and preserved(value) == value.original
    usage = quota_rows(live.guard)
    assert len(live.sent) == len(usage) == 4 and usage[:3] == value.old_usage
    assert len({row["attempt_id"] for row in usage}) == 4
    assert usage[-1]["status"] == kind and usage[-1]["run_id"] == run["id"]
    assert usage[-1]["role"] == "primary" and usage[-1]["lane"] == "eval"
    assert usage[-1]["model"] == value.binding.model and usage[-1]["scenario_id"] == value.binding.scenario_id
    linked = attempts(value)[value.pending_seq]["value"]["attempts"]
    assert linked[:-1] == value.old_attempts and len(linked) == len(value.old_attempts) + 1
    assert linked[-1]["state"] == "finished" and linked[-1]["result_kind"] == kind
    assert linked[-1]["attempt_id"] == usage[-1]["attempt_id"] and linked[-1]["terminal_sha256"] == fingerprint(
        usage[-1]
    )
    assert usage[-1]["attempt_id"] not in {row["attempt_id"] for row in value.old_usage}
    current = budget(value)
    assert current["segments"][:-1] == value.old_budget["segments"] and len(current["segments"]) == 2
    assert all(segment["phase"] == "closed" and segment["elapsed_ns"] > 0 for segment in current["segments"])
    assert {k: v for k, v in current.items() if k != "segments"} == {
        k: v for k, v in value.old_budget.items() if k != "segments"
    }
    summary = BudgetStore(target.repo, target.owner, value.binding, value.session).read_closed(run["id"])
    assert summary["consumed_ns"] == sum(segment["elapsed_ns"] for segment in current["segments"])
    assert summary["consumed_ns"] > sum(segment["elapsed_ns"] for segment in value.old_budget["segments"])
    return run, usage[-1]


def saved_state(value):
    record = value.control.load(value.session, value.binding, value.live.guard)
    assert record["revision"] == value.old_record["revision"] + 1
    return read_private(value.target.repo, value.target.owner, record, value.binding)


def test_case_effect_prefix_resumes_one_physical_attempt_then_native_final_and_completed_read(pending, record_property):
    value = pending
    value.live.primary = lambda request: wire({"type": "text", "text": value.answer})
    result = resume(value)
    run, terminal = assert_single_attempt_and_preserved_prefix(value, "ok")
    assert result.error is None and result.text == value.answer and result.model_calls == 4
    assert result.metadata["physical_model_requests"] == 4 and result.metadata["segment_model_requests"] == 1
    assert run["status"] == "succeeded" and run["lease_token"] is None
    assert result.metadata["run_id"] == run["id"] and len(result.receipts) == 2
    assert steps(value)[-1]["status"] == "completed" and steps(value)[-1]["seq"] == value.pending_seq
    assert sum(row["kind"] == "final" for row in rows(value, "core_run_events")) == 1
    assert saved_state(value)["phase"] == "primary_complete"
    before = core_state(value)
    assert value.target.completed_result(value.control, value.binding, value.live.guard).text == result.text
    assert core_state(value) == before
    assert len(value.live.sent) == 4 and terminal["finished_at"] is not None
    with pytest.raises(LifecycleError):
        value.target.send({"user": "attached send stays closed", "_index": 1})
    record_property("new_physical_attempts", 1)
    record_property("closed_execution_segments", 2)
    record_property("historical_case_effects_preserved", True)


def test_resumed_quota_appends_one_terminal_and_saves_new_pending_closed_checkpoint(pending, record_property):
    value = pending
    value.live.primary = lambda request: httpx.Response(
        403,
        headers={"Retry-After": "18000"},
        json={"error": {"type": "permission_error", "message": "5-hour usage limit"}},
    )
    with pytest.raises(ProviderStopped) as stopped:
        resume(value)
    assert stopped.value.reason == "quota_5h"
    run, terminal = assert_single_attempt_and_preserved_prefix(value, "quota_5h")
    last = steps(value)[-1]
    assert last["seq"] == value.pending_seq and last["status"] == "started"
    assert last["output"] is None and last["finished_at"] is None and last["usage"] == {}
    assert run["status"] == "running" and saved_state(value)["phase"] == "primary_pending"
    assert sum(row["kind"] == "final" for row in rows(value, "core_run_events")) == 0
    with value.live.guard.store.connect() as connection:
        account = value.live.guard.store.verify(connection)
        batches = connection.execute(
            sql.SQL("SELECT status,finished_at FROM {} WHERE account_id=%s").format(
                value.live.guard.store.table("core_model_batches")
            ),
            (value.live.guard.store.account_id,),
        ).fetchall()
    assert account["stop_kind"] == "quota_5h" and account["stopped_at"] == terminal["finished_at"]
    assert account["resume_at"] > account["stopped_at"]
    assert value.live.session._receipt is None and all(row["status"] == "completed" for row in batches)
    assert all(row["finished_at"] is not None for row in batches)
    record_property("new_physical_attempts", 1)
    record_property("closed_execution_segments", 2)
    record_property("new_pending_checkpoint_verified", True)


def test_actual_source_withdrawal_after_clear_is_refused_before_any_claim(pending, monkeypatch, record_property):
    from tools.eval.targets import v4_resume_pending

    value = pending
    original = v4_resume_pending.claim_pending
    claim = PostgresRepository.claim_run
    observed = {"entry": 0, "claim": 0, "success": 0}

    def withdraw_before_claim(handoff):
        observed["entry"] += 1
        assert_clear_without_post_or_new_epoch(value)
        with closing(PostgresRepository(value.target.dsn, schema=value.target.schema, initialize=False)) as independent:
            source = independent.get(value.target.owner, "message", value.run["request"]["source_message_id"])
            erased = SourceWithdrawalService(MemoryService(independent)).delete(
                value.target.owner,
                value.run["subject"],
                source["id"],
                expected_revision=source["revision"],
                request_id="quota-source-withdrawal-" + uuid.uuid4().hex,
            )
            assert erased["write_status"] == "deleted" and independent.is_revoked(
                value.target.owner, "message", source["id"]
            )
        observed["state_after_withdrawal"] = core_state(value)
        return original(handoff)

    def counted_claim(repo, *args, **kwargs):
        observed["claim"] += 1
        result = claim(repo, *args, **kwargs)
        observed["success"] += 1
        return result

    monkeypatch.setattr(v4_resume_pending, "claim_pending", withdraw_before_claim)
    monkeypatch.setattr(PostgresRepository, "claim_run", counted_claim)
    with pytest.raises(LifecycleError):
        resume(value)
    assert observed["entry"] == 1 and observed["claim"] == observed["success"] == 0
    assert core_state(value) == observed["state_after_withdrawal"]
    assert_clear_without_post_or_new_epoch(value, withdrawn=True)
    record_property("successful_claims", 0)
    record_property("new_physical_attempts", 0)
    record_property("actual_withdrawal_after_confirmed_clear", True)


def test_completed_history_change_before_authority_rejects_without_replaying_tools(
    pending, monkeypatch, record_property
):
    value = pending
    original = agent_model_history_evidence.completed_model_history
    observed = {}

    def change_after_real_proof(*args, **kwargs):
        repo = value.target.repo
        run = repo.fetch_run(value.target.owner, value.run["id"])
        before = core_state(value)
        with pytest.raises(ModelAttemptUnconfirmed):
            AgentRegenerator(repo).restart(run, _initial(repo, run))
        assert core_state(value) == before
        observed["regeneration_rejected"] = True
        proof = original(*args, **kwargs)
        assert "proof" not in observed and proof.execution_authority is False
        assert_clear_without_post_or_new_epoch(value)
        with closing(PostgresRepository(value.target.dsn, schema=value.target.schema, initialize=False)) as independent:
            current = independent.get(value.target.owner, "case", value.case["id"])
            changed = independent.update(
                value.target.owner,
                "case",
                current["id"],
                {"title": current["title"]},
                expected_revision=current["revision"],
            )
        assert changed["revision"] == current["revision"] + 1 and changed["state"] == current["state"]
        observed.update(proof=proof, changed=changed)
        return proof

    monkeypatch.setattr(agent_model_history_evidence, "completed_model_history", change_after_real_proof)
    with pytest.raises(ProviderStopped) as stopped:
        resume(value)
    assert stopped.value.reason == "ledger_unavailable" and observed["regeneration_rejected"]
    assert observed["proof"].seq < value.pending_seq
    assert value.target.repo.get(value.target.owner, "case", value.case["id"]) == observed["changed"]
    assert_clear_without_post_or_new_epoch(value)
    assert {key: row for key, row in preserved(value).items() if key != "case"} == {
        key: row for key, row in value.original.items() if key != "case"
    }
    assert attempts(value)[5]["value"]["attempts"] == value.old_attempts
    assert [row["seq"] for row in steps(value)] == [1, 2, 3, 4, 5] and steps(value)[-1]["status"] == "started"
    record_property("new_physical_attempts", 0)
    record_property("completed_history_lock_window_rejected", True)
    record_property("active_resume_regeneration_rejected_before_write", True)


def test_original_deadline_expired_after_witness_is_refused_before_clear(pending, monkeypatch, record_property):
    value = pending
    claims = []

    def reject_claim(*args, **kwargs):
        claims.append(True)
        pytest.fail("EXPIRED_RUN_MUST_NOT_REACH_CLAIM")

    monkeypatch.setattr(PostgresRepository, "claim_run", reject_claim)
    with eligible_quota5h(**arguments(value)) as witness:
        before = core_state(value), central(value), value.control.load(value.session, value.binding, value.live.guard)
        clock = get_clock()
        assert clock.now() < value.run["deadline_at"]
        set_clock(FrozenClock(value.run["deadline_at"] + timedelta(microseconds=1)))
        try:
            with pytest.raises(LifecycleError):
                value.target.resume_pending(
                    witness, control=value.control, binding=value.binding, guard=value.live.guard
                )
        finally:
            set_clock(clock)
        assert (
            core_state(value),
            central(value),
            value.control.load(value.session, value.binding, value.live.guard),
        ) == before
    assert not claims and len(value.live.sent) == 3 and quota_rows(value.live.guard) == value.old_usage
    record_property("new_physical_attempts", 0)
    record_property("expired_original_deadline_refused_before_clear", True)

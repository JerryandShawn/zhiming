"""One stored turn, native quota continuation and JudgeJournal; only HTTP is mocked."""

import copy
import time
from contextlib import contextmanager

import httpx
import pytest

from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock
from tools.eval.judge_journal import JudgeJournal
from tools.eval.lifecycle_identity import LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.session_driver import observe_session
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_execution_budget_store import BudgetStore
from tools.eval.targets.v4_lifecycle_state import read_private

from .test_eval_judge_journal_pg import completed as shared_completed
from .test_eval_lifecycle_pg import saved as shared_saved
from .test_eval_quota_resume_pending_pg import attempts, budget, steps
from .test_eval_quota_resume_pending_pg import pending as shared_pending
from .test_eval_quota_resume_pending_support import rows
from .test_eval_session_driver_support import assert_usage, bind, observer, physical, prefix, reader, whole_state
from .test_eval_v4_live_pg import live as shared_live
from .test_eval_v4_live_pg import wire


@pytest.fixture
def pending(p2_repo, monkeypatch):
    with (
        contextmanager(shared_live.__wrapped__)(p2_repo, monkeypatch) as live,
        contextmanager(shared_saved.__wrapped__)(live, monkeypatch) as value,
    ):
        bind(value)
        value.pending_seq = 3
        value.target.repo.renew_run(value.owner, value.run["id"], value.run["lease_token"], lease_seconds=1)
        time.sleep(1.15)
        with value.target.repo.transaction(value.owner) as connection:
            expired = connection.execute(
                "SELECT %s::timestamptz<=now() AS expired",
                (value.target.repo.fetch_run(value.owner, value.run["id"])["lease_until"],),
            ).fetchone()["expired"]
        assert expired is True
        value.live.session.close()
        with value.live.guard.store.connect() as connection:
            account = value.live.guard.store.verify(connection)
        assert account["stop_kind"] == "quota_5h" and account["resume_at"] is not None
        value.live.guard.clock = FrozenClock(account["resume_at"])
        value.old_usage = physical(value)
        assert len(value.old_usage) == len(value.live.sent) == 2
        value.old_pin = copy.deepcopy(value.run["usage"]["agent_runtime"]["limit_epochs"])
        value.old_budget = copy.deepcopy(budget(value))
        value.old_attempts = copy.deepcopy(attempts(value)[value.pending_seq]["value"]["attempts"])
        value.old_record = value.control.load(value.session, value.binding, value.live.guard)
        value.original = prefix(value)
        tool = value.original["steps"][-1]
        assert tool["seq"] == 2 and tool["kind"] == "tool" and tool["name"] == "memory_write"
        receipt = tool["output"]["receipt"]
        assert receipt["write_status"] == "saved"
        fact = value.target.repo.get(value.owner, "fact", receipt["fact_id"])
        source = value.target.repo.get(value.owner, "message", value.run["request"]["source_message_id"])
        quote = "我下周三有个面试"
        start = source["content"].index(quote)
        assert source["content"] == value.run["request"]["message"] and source["status"] == "active"
        assert fact["summary"] == "合成面试" and fact["content"] == quote and fact["revision"] == receipt["revision"]
        assert fact["status"] == "active" and fact["subject_id"] == source["subject_id"] == value.run["subject"]
        assert fact["source_refs"] == [
            {
                "message_id": source["id"],
                "version": source["revision"],
                "start": start,
                "end": start + len(quote),
                "quote": quote,
            }
        ]
        value.target.detach()
        with value.live.session.activate():
            yield value


@pytest.fixture
def noncanonical(p2_repo, monkeypatch, request):
    with contextmanager(shared_pending.__wrapped__)(p2_repo, monkeypatch, request) as value:
        bind(value)
        value.target.detach()
        yield value


@pytest.fixture
def completed(p2_repo, monkeypatch):
    with (
        contextmanager(shared_live.__wrapped__)(p2_repo, monkeypatch) as live,
        contextmanager(shared_completed.__wrapped__)(live, monkeypatch) as value,
    ):
        bind(value)
        value.live.session.close()
        yield value


def observe(value):
    target = observer(value)
    try:
        result = observe_session(
            target, value.control, value.session, value.binding, value.live.guard, value.live.judge()
        )
    finally:
        assert target.repo is None
    assert target.repo is None and target.schema == value.schema
    return result


def assert_native_prefix_and_budget(value, result):
    with reader(value) as current:
        run = current.target.repo.fetch_run(value.owner, value.run["id"])
        assert len(rows(current, "core_runs")) == 1 and run["retry_epoch"] == value.run["retry_epoch"]
        assert run["request"] == value.run["request"] and run["deadline_at"] == value.run["deadline_at"]
        assert run["usage"]["agent_runtime"]["limit_epochs"] == value.old_pin and prefix(value) == value.original
        actual = budget(current)
        assert actual["segments"][:-1] == value.old_budget["segments"] and len(actual["segments"]) == 2
        assert all(row["phase"] == "closed" and row["elapsed_ns"] > 0 for row in actual["segments"])
        summary = BudgetStore(current.target.repo, value.owner, value.binding, value.session).read_closed(run["id"])
        assert summary["consumed_ns"] == sum(row["elapsed_ns"] for row in actual["segments"])
        assert result["execution_usage"]["target_budget_wall_seconds"] == summary["consumed_ns"] / 10**9
        record = value.control.load(value.session, value.binding, value.live.guard)
        state = read_private(current.target.repo, value.owner, record, value.binding)
        return run, state, steps(current)


def test_pending_session_resumes_and_judges_once_then_new_observer_is_readonly(pending, record_property):
    value = pending
    value.live.primary = lambda request: wire({"type": "text", "text": "合成面试已保存，下周三可以复盘。"})
    first = observe(value)
    assert_usage(first, inherited=(2, 0), new=(1, 1), historical=(3, 1))
    assert first["session_id"] == value.session and first["scenario_id"] == value.binding.scenario_id
    assert first["turn"] == 1 and first["phase"] == "primary_complete"
    assert first["current_turn_completed"] is True and first["scenario_complete"] is True
    assert first["case"]["current_turn_score"] == first["case"]["score"]
    run, state, native = assert_native_prefix_and_budget(value, first)
    assert run["status"] == "succeeded" and run["lease_token"] is None
    assert state["phase"] == "primary_complete" and native[-1]["status"] == "completed"
    records = physical(value)
    assert len(records) == len(value.live.sent) == 4 and records[:2] == value.old_usage
    assert [row["role"] for row in records] == ["primary"] * 3 + ["critic"]
    with reader(value) as current:
        journal = current.target.repo.get(value.owner, "runtime_step", "eval-judge:" + value.session)
    assert journal["value"]["attempt_state"] == "completed"
    assert journal["value"]["result"]["score"] == 1 and journal["value"]["result"]["error"] is None
    assert journal["value"]["attempt_ids"] == [records[-1]["attempt_id"]]
    before = whole_state(value)
    second = observe(value)
    assert_usage(second, inherited=(3, 1), new=(0, 0), historical=(3, 1))
    assert second["case"]["current_turn_score"] == first["case"]["current_turn_score"]
    assert second["turn"] == first["turn"]
    assert second["case"] == first["case"] and whole_state(value) == before
    record_property("historical_physical_requests", 4)
    record_property("first_observer_new_requests", 2)
    record_property("second_observer_new_requests", 0)


def test_pending_session_quota_again_saves_checkpoint_without_judge_or_retry(pending, record_property):
    value = pending
    value.live.primary = lambda request: httpx.Response(
        403,
        headers={"Retry-After": "18000"},
        json={"error": {"type": "permission_error", "message": "5-hour usage limit"}},
    )
    result = observe(value)
    assert_usage(result, inherited=(2, 0), new=(1, 0), historical=(3, 0))
    assert result["phase"] == "primary_pending" and result["current_turn_completed"] is False
    assert result["scenario_complete"] is False and result["case"]["current_turn_score"] == 0
    assert result["case"]["stop_reason"] == "quota_5h"
    run, state, native = assert_native_prefix_and_budget(value, result)
    assert run["status"] == "running" and state["phase"] == "primary_pending"
    assert native[-1]["status"] == "started" and native[-1]["seq"] == value.pending_seq
    records = physical(value)
    assert len(records) == len(value.live.sent) == 3 and records[:2] == value.old_usage
    assert all(row["role"] == "primary" for row in records) and records[-1]["status"] == "quota_5h"
    with reader(value) as current:
        assert not [
            row for row in current.target.repo.list(value.owner, "runtime_step") if row.get("stage") == "eval_judge"
        ]
    record_property("new_target_requests", 1)
    record_property("new_judge_requests", 0)
    record_property("closed_execution_segments", 2)


def test_resumed_access_terminated_preserves_permanent_stop_without_new_checkpoint(pending, record_property):
    value = pending
    value.live.primary = lambda request: httpx.Response(
        403, json={"error": {"type": "permission_error", "message": "Access terminated"}}
    )
    with pytest.raises(ProviderStopped) as stopped:
        observe(value)
    assert stopped.value.reason == "access_terminated"
    records = physical(value)
    assert len(records) == len(value.live.sent) == 3 and records[:2] == value.old_usage
    assert all(row["role"] == "primary" for row in records) and records[-1]["status"] == "access_terminated"
    with value.live.guard.store.connect() as connection:
        account = value.live.guard.store.verify(connection)
    assert account["stop_kind"] == "access_terminated" and account["resume_at"] is None
    assert account["stopped_at"] == records[-1]["finished_at"]
    assert value.control.load(value.session, value.binding, value.live.guard) == value.old_record
    with reader(value) as current:
        run = current.target.repo.fetch_run(value.owner, value.run["id"])
        assert len(rows(current, "core_runs")) == 1 and run["retry_epoch"] == value.run["retry_epoch"]
        assert run["deadline_at"] == value.run["deadline_at"] and run["request"] == value.run["request"]
        assert run["usage"]["agent_runtime"]["limit_epochs"] == value.old_pin and prefix(value) == value.original
        actual = budget(current)
        assert actual["segments"][:-1] == value.old_budget["segments"] and len(actual["segments"]) == 2
        assert all(segment["phase"] == "closed" and segment["elapsed_ns"] > 0 for segment in actual["segments"])
        linked = attempts(current)[value.pending_seq]["value"]["attempts"]
        assert linked[:-1] == value.old_attempts and len(linked) == len(value.old_attempts) + 1
        assert linked[-1]["state"] == "finished" and linked[-1]["result_kind"] == "access_terminated"
        assert linked[-1]["attempt_id"] == records[-1]["attempt_id"]
        assert not [
            row for row in current.target.repo.list(value.owner, "runtime_step") if row.get("stage") == "eval_judge"
        ]
    record_property("new_target_requests", 1)
    record_property("new_judge_requests", 0)
    record_property("permanent_stop_preserved_without_new_checkpoint", True)


def test_actual_inflight_then_unknown_judge_is_preserved_without_repost(completed, record_property):
    value = completed
    with value.live.session.activate():
        journal = value.journal()
        inflight = journal._begin(value.live.judge())
        assert inflight["value"]["attempt_state"] == "inflight"
        value.target.detach()
        before = whole_state(value)
        with pytest.raises(LifecycleError):
            observe(value)
        assert whole_state(value) == before and len(value.live.sent) == 1
        target = observer(value)
        target.attach(value.control, value.session, value.binding, value.live.guard)
        journal = JudgeJournal(target, value.control, value.binding, value.live.guard)
        assert journal._unknown(inflight) is False
        assert journal.prepare()["value"]["attempt_state"] == "unknown"
        target.detach()
        before = whole_state(value)
        with pytest.raises(LifecycleError):
            observe(value)
        assert whole_state(value) == before and len(value.live.sent) == 1
    with reader(value) as current:
        actual = current.target.repo.fetch_run(value.owner, value.run["id"])
    assert actual["retry_epoch"] == value.run["retry_epoch"] and actual["status"] == "succeeded"
    record_property("new_judge_requests", 0)
    record_property("ambiguous_score_never_reposted", True)


def test_noncanonical_saved_turn_rejects_driver_before_resume_judge_or_claim(
    noncanonical, monkeypatch, record_property
):
    value = noncanonical
    case = next(case for case in load_core30() if case.id == value.binding.scenario_id)
    assert value.run["request"]["message"] != case.turns[0].user
    before = whole_state(value)

    def forbidden(*args, **kwargs):
        pytest.fail("NONCANONICAL_SESSION_MUST_NOT_INITIALIZE_RESUME_CLAIM_OR_JUDGE")

    for cls, name in (
        (type(value.control), "initialize"),
        (PostgresRepository, "claim_run"),
        (type(value.target), "resume_pending"),
        (JudgeJournal, "evaluate"),
    ):
        monkeypatch.setattr(cls, name, forbidden)
    with pytest.raises(LifecycleError):
        observe(value)
    assert whole_state(value) == before and len(value.live.sent) == 3
    with reader(value) as current:
        run = current.target.repo.fetch_run(value.owner, value.run["id"])
    assert run["status"] == "running" and run["request"] == value.run["request"]
    assert run["retry_epoch"] == value.run["retry_epoch"]
    record_property("new_physical_requests", 0)
    record_property("noncanonical_saved_turn_rejected_before_execution", True)

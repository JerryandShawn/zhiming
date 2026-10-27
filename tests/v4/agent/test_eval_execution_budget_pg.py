"""Real PG execution segments, actual monotonic waiting and read-only lifecycle."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

from mingjing_core.agent.runtime_config import validate_runtime_config
from mingjing_core.application.runtime_limits import RuntimeLimits
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval import lifecycle_identity
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_durable import DurableCore30Target
from tools.eval.targets.v4_execution_budget_store import BudgetStore
from tools.eval.targets.v4_lifecycle_state import read_private

from .test_eval_lifecycle_pg import seed
from .test_eval_v4_live_pg import Harness, wire
from .test_eval_v4_live_pg import live as live_fixture


@pytest.fixture
def live(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from live_fixture.__wrapped__(p2_repo, monkeypatch)


@dataclass
class Case:
    live: Harness
    target: DurableCore30Target
    binding: LifecycleBinding
    control: LifecycleControl
    scenario: Any

    def send(self) -> Any:
        turn = self.scenario.turns[0].model_dump(mode="json", exclude={"expect"})
        with self.live.session.activate(), call_scope(self.live.session.scope("M01")):
            return self.target.send(dict(turn, _index=1))

    def store(self) -> BudgetStore:
        return BudgetStore(self.target.repo, self.target.owner, self.binding, self.target.lifecycle_session)

    def run(self) -> dict[str, Any]:
        return self.target.repo.fetch_run(self.target.owner, self.target.run_ids[-1])

    def new(self) -> DurableCore30Target:
        target = DurableCore30Target(
            model=self.binding.model,
            dsn=self.target.dsn,
            environment=self.live.environment,
            adapter_factory=self.live.factory,
        )
        self.live.targets.append(target)
        return target


@pytest.fixture
def cases(live: Harness, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[], Case]]:
    # Only clean-checkout discovery is simulated for this WIP test. The actual
    # source digest, central PG identity and all business effects remain real.
    monkeypatch.setattr(lifecycle_identity, "candidate_provenance", lambda *args: {"worktree_clean": True})
    scenario = next(case for case in load_core30() if case.id == "M01")
    control = LifecycleControl(live.guard.store.dsn, "eval_control_" + uuid.uuid4().hex)
    control.initialize(live.guard)
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(scenario.clock)))

    def create() -> Case:
        binding = LifecycleBinding.capture(live.guard, "a" * 40, scenario, "k3-256k")
        target = DurableCore30Target(
            model=binding.model, dsn=live.guard.store.dsn, environment=live.environment, adapter_factory=live.factory
        )
        live.targets.append(target)
        target.reset(seed(scenario))
        return Case(live, target, binding, control, scenario)

    try:
        yield create
    finally:
        set_clock(previous)
        with psycopg.connect(live.guard.store.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(control.schema)))


def _budget(case: Case) -> dict[str, Any]:
    run = case.run()
    row = case.target.repo.get(case.target.owner, "runtime_step", BudgetStore.ident(run["id"], run["retry_epoch"]))
    return row["budget"]


def _pin(case: Case) -> tuple[dict, Any]:
    run = case.run()
    return run["usage"]["agent_runtime"]["limit_epochs"][str(run["retry_epoch"])], run["deadline_at"]


def _assert_written_fact(case: Case) -> None:
    target, run = case.target, case.run()
    with target.repo.transaction(target.owner) as connection:
        steps = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE owner=%s AND run_id=%s AND kind='tool' "
                "AND name='memory_write' AND status='completed'"
            ).format(target.repo.table("core_run_steps")),
            (target.owner, run["id"]),
        ).fetchall()
    assert len(steps) == 1 and steps[0]["output"]["receipt"]["write_status"] == "saved"
    receipt = steps[0]["output"]["receipt"]
    fact = target.repo.get(target.owner, "fact", receipt["fact_id"])
    source = target.service.memory.get_source(target.owner, target.bindings["turn-1"])
    quote = "我下周三有个面试"
    start = source["content"].index(quote)
    assert fact["id"] not in target.seeder.profile_fact_ids and fact["status"] == "active"
    assert fact["summary"] == "合成面试" and fact["content"] == quote
    assert fact["source_refs"] == [
        dict(message_id=source["id"], version=source["revision"], start=start, end=start + len(quote), quote=quote)
    ]


def test_multiple_model_monitors_close_one_successful_segment_then_readonly_attach_preserves_budget(
    cases: Callable[[], Case], record_property: Callable[[str, object], None]
) -> None:
    case = cases()
    observed_phases = []

    def respond(request: httpx.Request) -> httpx.Response:
        observed_phases.append(_budget(case)["segments"][-1]["phase"])
        time.sleep(0.02)
        if len(observed_phases) == 1:
            return wire(
                {
                    "type": "tool_use",
                    "id": "budget-memory",
                    "name": "memory_write",
                    "input": {
                        "message_id": case.target.bindings["turn-1"],
                        "quote": "我下周三有个面试",
                        "summary": "合成面试",
                        "kind": "event",
                        "date_expression": "下周三",
                    },
                }
            )
        return wire({"type": "text", "text": "已记下这次面试。"})

    case.live.primary = respond
    result = case.send()
    run = case.run()
    assert result.error is None and run["status"] == "succeeded" and run["lease_token"] is None
    assert observed_phases == ["open", "open"] and len(case.live.sent) == 2
    before = case.store().read_closed(run["id"])
    assert before["segments"] == 1 and before["consumed_ns"] >= 40_000_000
    _assert_written_fact(case)
    with pytest.raises(LifecycleError, match="未持久保存"):
        case.target.detach()
    pin = _pin(case)
    session = case.target.checkpoint(case.control, case.binding, case.live.guard, turn=1, completed=result)
    case.target.detach()
    attached = case.new()
    attached.attach(case.control, session, case.binding, case.live.guard)
    actual = BudgetStore(attached.repo, attached.owner, case.binding, session).read_closed(run["id"])
    assert (
        actual == before and attached.completed_result(case.control, case.binding, case.live.guard).text == result.text
    )
    restored = attached.repo.fetch_run(attached.owner, run["id"])
    assert (restored["usage"]["agent_runtime"]["limit_epochs"][str(run["retry_epoch"])], restored["deadline_at"]) == pin
    with pytest.raises(LifecycleError):
        attached.send({"user": "must stay observation-only", "_index": 1})
    assert len(case.live.sent) == 2
    record_property("physical_mock_requests", 2)
    record_property("logical_model_steps", 2)
    record_property("execution_segments", 1)
    record_property("closed_monotonic_ns", before["consumed_ns"])


def test_real_monotonic_exhaustion_rejects_next_attempt_before_any_post_without_resetting_pin(
    cases: Callable[[], Case], monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    case = cases()
    config = case.target.runtime.config.model_dump()
    config["interactive"]["max_seconds"] = 1
    case.target.runtime.config = validate_runtime_config(config)
    original = case.target.runtime.control_factory

    def actual_work(*args: Any, **kwargs: Any) -> Any:
        control = original(*args, **kwargs)
        time.sleep(1.1)
        return control

    case.target.runtime.control_factory = actual_work
    with pytest.raises(ProviderStopped) as first_stop:
        case.send()
    record_property("first_stop_kind", first_stop.value.reason)
    assert first_stop.value.reason == "ledger_unavailable" and first_stop.value.model_calls == 0
    assert case.target._budget_unknown is False and case.live.sent == []
    run, pin = case.run(), _pin(case)
    before = case.store().read_closed(run["id"])
    assert before["consumed_ns"] >= 1_100_000_000 and before["segments"] == 1
    case.target.runtime.control_factory = original
    original_open, rejections = BudgetStore.open, []

    def observed_open(store: BudgetStore, *args: Any, **kwargs: Any) -> tuple[int, bool]:
        try:
            return original_open(store, *args, **kwargs)
        except LifecycleError as error:
            rejections.append("cumulative_exhausted" if str(error) == "累计执行预算已耗尽" else "other_lifecycle_error")
            raise

    monkeypatch.setattr(BudgetStore, "open", observed_open)
    with case.live.session.activate(), call_scope(case.live.session.scope("M01")), pytest.raises(ProviderStopped):
        case.target._attempt(run, [])
    assert rejections == ["cumulative_exhausted"] and case.live.sent == []
    assert case.store().read_closed(run["id"]) == before and _pin(case) == pin
    record_property("actual_wait_seconds", "1.1")
    record_property("closed_monotonic_ns", before["consumed_ns"])
    record_property("next_attempt_rejection", rejections[0])
    record_property("physical_mock_requests", 0)


def _interrupted(case: Case) -> dict[str, Any]:
    stop = KeyboardInterrupt("synthetic process-control boundary")

    def interrupt(request: httpx.Request) -> httpx.Response:
        raise stop

    case.live.primary = interrupt
    with pytest.raises(KeyboardInterrupt) as caught:
        case.send()
    assert caught.value is stop and case.store().read_closed(case.run()["id"])["segments"] == 1
    case.target.checkpoint(case.control, case.binding, case.live.guard, turn=1)
    return case.run()


def _legacy_queued(case: Case) -> None:
    target, turn = case.target, case.scenario.turns[0]
    source = ThreadService(target.repo).receive(
        target.owner, target.thread["id"], turn.user, request_id="legacy-budget-source"
    )
    target.bindings["turn-1"] = source["id"]
    run = ThreadIngress(target.service).queue(
        owner=target.owner,
        thread_id=target.thread["id"],
        source_ids=[source["id"]],
        request_id="legacy-budget-queued",
        conversation_id="shared",
        case_ids=target.seeder.case_ids,
        depth="standard",
    )
    assert run["status"] == "queued"
    target.run_ids.append(run["id"])
    session = target.checkpoint(case.control, case.binding, case.live.guard, turn=1)
    record = case.control.load(session, case.binding, case.live.guard)
    assert "execution_budget" not in read_private(target.repo, target.owner, record, case.binding)
    target.detach()
    attached = case.new()
    attached.attach(case.control, session, case.binding, case.live.guard)
    assert attached._budget_legacy and attached.repo.fetch_run(attached.owner, run["id"])["status"] == "queued"
    with pytest.raises(LifecycleError):
        attached.send({"user": "legacy is not zero seconds", "_index": 1})


def test_unknown_open_missing_journal_budget_and_queued_legacy_never_gain_execution_authority(
    cases: Callable[[], Case], record_property: Callable[[str, object], None]
) -> None:
    orphan = cases()
    run = _interrupted(orphan)
    closed = orphan.store().read_closed(run["id"])
    changed = BudgetStore(
        orphan.target.repo, orphan.target.owner, replace(orphan.binding, model="k3"), orphan.target.lifecycle_session
    )
    with pytest.raises(LifecycleError, match="不属于"):
        changed.read_closed(run["id"])
    assert orphan.store().read_closed(run["id"]) == closed
    policy = RuntimeLimits(orphan.target.repo).policy(run, orphan.target.runtime.config)
    orphan.store().open(run, policy)
    before = len(orphan.live.sent)
    with pytest.raises(LifecycleError, match="未闭合"):
        orphan.target.detach()
    assert len(orphan.live.sent) == before and _budget(orphan)["segments"][-1]["phase"] == "open"
    missing = cases()
    run = _interrupted(missing)
    with missing.target.repo.transaction(missing.target.owner) as connection:
        connection.execute(
            sql.SQL("DELETE FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                missing.target.repo.table("core_entities")
            ),
            (missing.target.owner, BudgetStore.ident(run["id"], run["retry_epoch"])),
        )
    before = len(missing.live.sent)
    with missing.live.session.activate(), call_scope(missing.live.session.scope("M01")), pytest.raises(ProviderStopped):
        missing.target._attempt(run, [])
    assert len(missing.live.sent) == before
    _legacy_queued(cases())
    assert len(missing.live.sent) == before
    record_property("unknown_open", "refused; actual open retained")
    record_property("missing_budget_with_journal", "refused before POST")
    record_property("queued_legacy", "read-only; elapsed unknown; attached send closed")

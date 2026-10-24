"""Observe one existing durable core30 turn; never create or reset an evaluation run."""

from __future__ import annotations

import re
from datetime import datetime

from mingjing_core.application.agent_regeneration import AgentRegenerator
from mingjing_core.models.quota_delegated_session import DelegatedSession, require_active
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import fingerprint
from tools.eval.engine import _case, _record_stop
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.quota_resume_evidence import require, typed
from tools.eval.quota_resume_witness import eligible_quota5h
from tools.eval.session_accounting import reconcile, snapshot
from tools.eval.session_grading import grade_current
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_durable import DurableCore30Target
from tools.eval.targets.v4_execution_budget import _failure
from tools.eval.targets.v4_execution_budget_store import BudgetStore
from tools.eval.targets.v4_lifecycle_state import read_private
from tools.eval.targets.v4_live_judge import V4LiveJudge


def _inputs(target, control, session_id, binding, guard, judge):
    require(type(target) is DurableCore30Target and target.repo is None and target.lifecycle_session is None)
    require(type(control) is LifecycleControl and type(binding) is LifecycleBinding and type(judge) is V4LiveJudge)
    require(type(guard) is QuotaGuard)
    require(re.fullmatch(r"eval-[a-f0-9]{32}", session_id or "") is not None)
    active = require_active()
    require(
        type(active) is DelegatedSession
        and active.phase == "core"
        and active.guard is guard
        and active.approval.candidate == binding.candidate_commit
        and target.model == binding.model
        and binding.scenario_id in active.scenarios
        and active._receipt is None
    )
    binding.verify(guard)
    handles = judge.provider.tracker.port.registry.resolve("critic")
    require(handles and all(handle.model == binding.model for handle in handles))
    return active


def _state(target, control, binding, guard):
    record = control.load(target.lifecycle_session, binding, guard)
    return read_private(target.repo, target.owner, record, binding)


def _bound_turn(target, scenario, state):
    index = state["turn"]
    require(type(index) is int and 1 <= index <= len(scenario.turns))
    turn, run = scenario.turns[index - 1], target.repo.fetch_run(target.owner, state["runs"][-1]["id"])
    operation = f"v4-eval:{scenario.id}:{index}"
    source_id = target.bindings.get(f"turn-{index}")
    source = target.repo.get(target.owner, "message", source_id)
    require(
        turn.channel in {"web", "tarot"}
        and run["operation_id"] == operation
        and run["request"]["message"] == source["content"] == turn.user
        and run["request"]["source_message_id"] == source_id
        and run["request"].get("source_message_ids") == [source_id]
        and source.get("channel") == turn.channel
        and source.get("role") == "user"
        and source.get("thread_id") == state["thread_id"]
        and source["subject_id"] == run["subject"]
        and source.get("source_id") == "thread-source:" + fingerprint([state["thread_id"], operation])
        and datetime.fromisoformat(state["business_clock"]) == datetime.fromisoformat(turn.at or scenario.clock)
        and datetime.fromisoformat(source["at"]) == datetime.fromisoformat(turn.at or scenario.clock)
    )
    with target.repo.transaction() as connection:
        AgentRegenerator(target.repo)._proven_request(connection, run, run)


def _close_repository(target):
    repo, target.repo = target.repo, None
    if repo is not None:
        repo.close()


def _release(target, active, failure):
    try:
        active.close()
    except BaseException as error:
        failure = _failure(failure, error)
    try:
        if target.repo is not None:
            if target._budget_scope is not None or target._budget_unknown:
                raise LifecycleError("SESSION_OBSERVATION_BUDGET_NOT_CLOSED")
            target.detach()
    except BaseException as error:
        failure = _failure(failure, error)
        try:
            _close_repository(target)
        except BaseException as closing:
            failure = _failure(failure, closing)
    return failure


def _pending(target, control, binding, guard, scenario, state):
    try:
        with eligible_quota5h(target, control, binding, guard) as witness:
            target.resume_pending(witness, control=control, binding=binding, guard=guard)
    except ProviderStopped as stopped:
        if stopped.reason != "quota_5h":
            raise
        try:
            state = _state(target, control, binding, guard)
            require(state["phase"] == "primary_pending" and not target._budget_unknown)
        except (KeyboardInterrupt, SystemExit, GeneratorExit):
            raise
        except BaseException:
            stopped.add_note("SESSION_PENDING_CHECKPOINT_NOT_CONFIRMED")
            raise stopped from None
        case = _case(scenario.id, scenario.category, "incomplete")
        _record_stop(case, stopped.reason, stopped.role, stopped.provider_http_status, stopped.resume_at)
        case.update(
            observed_turn=state["turn"],
            current_turn_score=0.0,
            current_turn_completed=False,
            scenario_complete=False,
            business_clock=scenario.clock,
        )
        return case, stopped
    return None, None


def _observe_attached(target, control, binding, guard, judge):
    state = _state(target, control, binding, guard)
    scenario = next(case for case in load_core30() if case.id == binding.scenario_id)
    _bound_turn(target, scenario, state)
    external_before = (target.port.external_calls, judge.provider.tracker.external_calls)
    before = snapshot(target, control, binding, guard, state)
    case, stopped = (
        _pending(target, control, binding, guard, scenario, state)
        if state["phase"] == "primary_pending"
        else (None, None)
    )
    try:
        state = _state(target, control, binding, guard)
        _bound_turn(target, scenario, state)
        if case is None:
            require(state["phase"] == "primary_complete")
            case = grade_current(target, control, binding, guard, judge, scenario, state)
        require_active().close()
        after = snapshot(target, control, binding, guard, state)
        return _observation(target, binding, guard, judge, scenario, state, case, before, after, external_before)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException:
        if stopped is not None:
            stopped.add_note("SESSION_STOP_ACCOUNTING_NOT_CONFIRMED")
            raise stopped from None
        raise


def _observation(target, binding, guard, judge, scenario, state, case, before, after, external_before):
    usage = reconcile(before, after)
    case.update(usage["historical_actual_usage"])
    budget = BudgetStore(target.repo, target.owner, binding, target.lifecycle_session).read_closed(
        state["runs"][-1]["id"]
    )
    require(budget is not None)
    usage["target_budget_wall_seconds"] = budget["consumed_ns"] / 10**9
    case["v4_evidence"] = {
        "offline": False,
        "runtime": "v4",
        "external_provider_requests": target.port.external_calls - external_before[0],
        "judge_external_provider_requests": judge.provider.tracker.external_calls - external_before[1],
        "external_request_basis": "current_observation_only",
        "physical_evidence_sha256": fingerprint(after.rows),
        "current_saved_turn_only": True,
    }
    return dict(
        case=case,
        execution_usage=usage,
        session_id=target.lifecycle_session,
        scenario_id=scenario.id,
        turn=state["turn"],
        phase=state["phase"],
        current_turn_completed=case["current_turn_completed"],
        scenario_complete=case["scenario_complete"],
    )


def observe_session(target, control, session_id, binding, guard, judge) -> dict:
    """Only a sealed live core session can attach/continue/score this one saved turn."""
    active = _inputs(target, control, session_id, binding, guard, judge)
    failure, observation = None, None
    try:
        target.attach(control, session_id, binding, guard)
        typed(target, control, binding, guard)
        observation = _observe_attached(target, control, binding, guard, judge)
    except BaseException as error:
        failure = error
    failure = _release(target, active, failure)
    if failure is not None:
        raise failure
    return observation


def _report(args, scenarios, config, model, observation):
    from tools.eval.runner import _metadata

    metadata = _metadata(config, args.mode, args.target, model)
    metadata.update(getattr(args, "candidate_provenance", {}))
    metadata.update(
        evaluation_suite="core30",
        status="incomplete",
        planned_scenario_ids=[case.id for case in scenarios],
        execution_usage=observation["execution_usage"],
        lifecycle_session=observation["session_id"],
        lifecycle_scenario=observation["scenario_id"],
        lifecycle_turn=observation["turn"],
        lifecycle_phase=observation["phase"],
        observation_unit="one_existing_saved_session_turn",
        automatic_initial_or_future_turns=False,
    )
    case, usage = observation["case"], observation["execution_usage"]
    for name in (
        "stop_reason",
        "stop_role",
        "requires_user_decision",
        "resume_at",
        "automatic_resume_eligible",
        "permanent_stop",
        "provider_http_status",
    ):
        if name in case:
            metadata[name] = case[name]
    batch = dict(
        attempt=1,
        batch=1,
        scenario_ids=[case["id"]],
        unit="one_existing_session_observation_not_HTTP_batch",
        executed_ids=[case["id"]] if usage["new"]["total"] else [],
        cached_ids=[case["id"]] if usage["inherited"]["total"] else [],
        new_usage=usage["new_usage"],
        inherited_usage=usage["inherited_usage"],
        status="stopped" if case.get("stop_reason") else "complete",
    )
    return dict(metadata=metadata, cases=[case], batches=[batch])


def run_session(args, scenarios, config, model, active):
    """Called inside the original live gate after equivalence selected exactly one model."""
    import argparse
    import os

    from tools.eval.runner import EVAL_ROOT, _finish, _publish_contract_report

    scenario = next(case for case in scenarios if case.id == args.lifecycle_scenario)
    binding = LifecycleBinding.capture(active.guard, args.candidate, scenario, model)
    control = LifecycleControl(os.getenv("CORE_TEST_DSN", ""), args.lifecycle_schema)
    target = DurableCore30Target(model=model)
    judge = V4LiveJudge(model, EVAL_ROOT / config["judge"]["rubric"])
    observation = observe_session(target, control, args.lifecycle_session, binding, active.guard, judge)
    output = argparse.Namespace(**vars(args))
    output.output = args.output / "lifecycle" / args.lifecycle_session
    report = _report(args, scenarios, config, model, observation)
    _publish_contract_report(report, output.output, {case.id: case for case in scenarios})
    return _finish(output, scenarios, report)

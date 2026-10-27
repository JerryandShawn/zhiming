"""Explicitly injected life-thread RuntimePort; no provider or delivery construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from mingjing_core.agent.context import ContextEngine
from mingjing_core.agent.context_tokens import TokenMeter
from mingjing_core.agent.context_types import (
    BudgetPolicy,
    ContextBuild,
    ContextInputError,
)
from mingjing_core.agent.crisis import fallback_text
from mingjing_core.agent.journal import Journal
from mingjing_core.agent.loop_cycle import LoopCycle, LoopOutcome
from mingjing_core.agent.loop_policy import LoopPolicy, RunControl
from mingjing_core.agent.prompts import load_prompts
from mingjing_core.agent.runtime_config import (
    RuntimeConfig,
    RuntimeConfigError,
    load_runtime_config,
    validate_runtime_config,
)
from mingjing_core.agent.toolkit import ToolRegistry
from mingjing_core.application.agent_answer_text import without_history_header
from mingjing_core.application.agent_finalization import AgentFinalizer
from mingjing_core.application.agent_memory_receipts import MemoryReceiptEvents
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_regeneration import AgentRegenerator
from mingjing_core.application.agent_review import AgentReviewer
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.agent_runtime_state import RuntimeState
from mingjing_core.application.agent_snapshots import AgentSnapshotStore
from mingjing_core.application.agent_thread_scope import thread_id
from mingjing_core.application.agent_tools import AgentToolsService
from mingjing_core.application.agent_tools_clarification import (
    apply_clarification_answer,
)
from mingjing_core.application.agent_tools_private import consume_private_answer
from mingjing_core.application.memory import MemoryService
from mingjing_core.application.read_result import read_result
from mingjing_core.application.run_event_stream import ModelDeltaStream
from mingjing_core.application.runtime_limits import RuntimeLimits
from mingjing_core.application.time_range_parser import ModuleTimeRangeParser
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.models.port import ModelPort
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import get_clock


class AgentRuntime:
    def __init__(
        self,
        repo: PostgresRepository,
        port: ModelPort,
        meter: TokenMeter,
        *,
        critic: ModelPort | None = None,
        critic_meter: TokenMeter | None = None,
        offline: bool = False,
        budget: BudgetPolicy | None = None,
        control_factory: Callable[..., RunControl] = RunControl,
        runtime_config: RuntimeConfig | None = None,
        streaming_candidate: bool = False,
    ) -> None:
        if type(streaming_candidate) is not bool:
            raise EvidenceError("流式候选开关只能由受信程序集明确配置")
        if runtime_config is not None and type(runtime_config) is not RuntimeConfig:
            raise RuntimeConfigError("运行安全配置只能由受信构造注入")
        self.config = load_runtime_config() if runtime_config is None else validate_runtime_config(runtime_config)
        self.repo, self.port, self.offline = repo, port, offline
        self.meter, self.budget = meter, budget or BudgetPolicy()
        self.prompts, self.state = load_prompts(), RuntimeState(repo)
        self.ledger = RequestLedger(repo, meter, offline=offline)
        self.reviewer = AgentReviewer(
            critic,
            RequestLedger(repo, critic_meter or meter, offline=offline),
            self.prompts,
            offline=offline,
        )
        self.control_factory = control_factory
        self.streaming_candidate = streaming_candidate

    def _snapshot(self, run: dict[str, Any], system: str) -> ContextBuild:
        engine = ContextEngine(
            MemoryService(self.repo),
            system,
            clock=get_clock(),
            policy=self.budget,
            token_meter=self.ledger.meter(run),
        )
        return AgentSnapshotStore(self.repo).load_or_build(
            run,
            lambda: engine.build(
                run["owner"],
                run["request"]["source_message_id"],
                subject=run["subject"],
                thread_id=thread_id(run),
                case_ids=tuple(run["request"].get("case_ids", [])),
                run_context=run,
            ),
        )

    def _cycle(
        self,
        run: dict[str, Any],
        frozen: ContextBuild,
        events: RuntimeEvents,
        *,
        crisis: bool,
        policy: LoopPolicy,
    ) -> LoopCycle:
        policy = replace(policy, text_only=crisis)
        control = self.control_factory(self.repo, run, policy, no_text_seconds=20 if crisis else None)
        return LoopCycle(
            self.port,
            ToolRegistry(AgentToolsService(self.repo, relative_parser=ModuleTimeRangeParser())),
            Journal(self.repo, run["owner"]),
            run,
            frozen,
            policy=policy,
            token_meter=self.meter,
            offline=self.offline,
            control=control,
            budget_policy=self.budget,
            crisis=crisis,
            incognito=thread_id(run).startswith("incognito:"),
            ledger=self.ledger,
            emit=events.send,
            tool_emit=events.tool_event,
            text_stream=ModelDeltaStream(
                self.repo, run, self.ledger, events.callback, cancel_event=control.cancel_event
            )
            if self.streaming_candidate
            else None,
            memory_receipts=MemoryReceiptEvents(events) if self.streaming_candidate else None,
        )

    def _start(self, run: dict[str, Any], events: RuntimeEvents) -> None:
        request = run["request"]
        events.send(
            "started",
            {
                "thread_id": thread_id(run),
                "message_id": request["source_message_id"],
                "incognito": thread_id(run).startswith("incognito:"),
                **{name: request[name] for name in ("area_id", "topic_id") if request.get(name)},
            },
        )
        events.send("status", {"text": "我在认真看你的话", "phase": "thinking"})

    def _finish(
        self,
        cycle: LoopCycle,
        outcome: LoopOutcome,
        events: RuntimeEvents,
        *,
        crisis: bool,
    ) -> dict[str, Any]:
        stopped = outcome.stop_reason
        if stopped in {
            "cancelled",
            "model_cancelled",
            "wall_time_limit",
            "lease_or_source_invalid",
            "lease_or_dependency_invalid",
            "source_revoked",
            "source_changed",
            "dependencies_changed",
            "runtime_identity_changed",
            "control_failure",
        }:
            raise EvidenceError("本轮已经停止或来源失效，不能发布正文")
        review = None
        if stopped.startswith("model_") or stopped == "empty_answer":
            outcome = replace(outcome, text=fallback_text(), asked=None)
            self.state.metadata(cycle.run, fallback="availability_template", fallback_reason=stopped)
            # Any partial draft is explicitly superseded by the audited template.
            events.send("text_reset", {"text": outcome.text, "reason": "resumed"})
        else:
            from mingjing_core.application.agent_sensitive_pending import ensure_sensitive_pending

            cleaned = without_history_header(outcome.text)
            if cleaned != outcome.text:
                outcome = replace(outcome, text=cleaned)
                events.send("text_reset", {"text": cleaned, "reason": "resumed"})
            outcome = ensure_sensitive_pending(cycle, outcome)
            outcome, review = self.reviewer.review(cycle, outcome)
        self.state.metadata(cycle.run, crisis=crisis)
        envelope = AgentFinalizer(self.repo).finalize(
            cycle.run,
            text=outcome.text,
            alias_map=outcome.alias_map,
            versions=outcome.versions,
            snapshot_revision=cycle.frozen.snapshot_revision,
            asked=outcome.asked,
            usage=outcome.usage,
            review=review,
        )
        if envelope["asked"]:
            events.send("ask_user", envelope["asked"])
        if envelope["options"]:
            events.send("present_options", envelope["options"])
        events.send("final", {"message_id": envelope["message_id"], "envelope": envelope})
        return envelope

    def execute(self, service: Any, owner: str, run_id: str, lease_token: str, emit: Any = None) -> dict[str, Any]:
        if getattr(service, "repo", None) is not self.repo:
            raise ScopeError("运行服务与仓库不属于同一受信实例")
        current = self.repo.fetch_run(owner, run_id)
        if current["status"] == "succeeded":
            read_result(current["result"])
            return current["result"]
        run = self.state.authority(owner, run_id, lease_token)
        apply_clarification_answer(self.repo, run)
        events = RuntimeEvents(self.repo, run, emit)
        self._start(run, events)
        confirmation = consume_private_answer(self.repo, run)
        if confirmation:
            self.state.metadata(run, private_reminder_status=confirmation["write_status"])
        for attempt in range(2):
            policy = RuntimeLimits(self.repo).policy(run, self.config)
            crisis = False
            system = self.prompts.system(onboarding=self.state.onboarding(run), crisis=crisis)
            if confirmation:
                system += (
                    "\n本轮单独提醒确认已由程序处理，提醒状态：" + confirmation["write_status"] + "。这不是长期记忆。"
                )
            self.state.pin(run, self.prompts, system, crisis=crisis)
            try:
                frozen = self._snapshot(run, system)
            except ContextInputError as error:
                from mingjing_core.application.agent_crisis_fallback import (
                    commit_unavailable_template,
                )

                return commit_unavailable_template(self.repo, run, events, reason=error.code)
            cycle = self._cycle(run, frozen, events, crisis=crisis, policy=policy)
            try:
                outcome = cycle.execute()
                return self._finish(cycle, outcome, events, crisis=cycle.crisis)
            except ContextInputError as error:
                from mingjing_core.application.agent_crisis_fallback import (
                    commit_unavailable_template,
                )

                return commit_unavailable_template(self.repo, run, events, reason=error.code)
            except CoreError:
                used = replace(frozen, injected_versions=cycle.versions)
                if attempt or not AgentRegenerator(self.repo)._related(run, used):
                    raise
                previous = run
                run = AgentRegenerator(self.repo).restart(run, used)
                if callable(handoff := getattr(service, "agent_lease_changed", None)):
                    handoff(previous, run)
                events.run = run
                events.begin_epoch()
                events.send("text_reset", {"text": "", "reason": "resumed"})
        raise EvidenceError("本轮重新生成次数已用尽")

    def purge(self, run_id: str, epoch: int) -> None:
        # v4 has no external graph/checkpointer. PrivacyService owns PG deletion.
        if not isinstance(run_id, str) or type(epoch) is not int or epoch < 0:
            raise EvidenceError("清理身份无效")


class RuntimeRouter:
    """Select by the authoritative persisted runtime, never by caller input."""

    def __init__(self, repo: PostgresRepository, legacy: Any, agent: AgentRuntime) -> None:
        self.repo, self.legacy, self.agent = repo, legacy, agent

    def execute(self, service: Any, owner: str, run_id: str, lease_token: str, emit: Any = None) -> dict[str, Any]:
        runtime = self.repo.fetch_run(owner, run_id)["runtime"]
        if runtime not in {"v3", "v4"}:
            raise EvidenceError("未知运行版本")
        target = self.agent if runtime == "v4" else self.legacy
        return target.execute(service, owner, run_id, lease_token, emit)

    def purge(self, run_id: str, epoch: int) -> None:
        self.legacy.purge(run_id, epoch)

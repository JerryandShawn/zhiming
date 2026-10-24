"""Recoverable model/tool cycle only; RuntimePort, final commit and events are separate."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_model_attempts import confirmed
from mingjing_core.application.agent_model_calls import RequestLedger
from mingjing_core.application.agent_thread_scope import thread_id
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict
from mingjing_core.models.errors import ModelProtocolError, ModelUnavailable
from mingjing_core.models.port import ChatMessage, ModelPort, ToolCall
from mingjing_core.models.quota_attempt_observer import ModelAttemptUnconfirmed

from .context_budget import assert_live_allowed
from .context_tokens import TokenMeter, apply_token_budget
from .context_types import (
    BudgetPolicy,
    ContextBuild,
    ContextInputError,
    ContextItem,
    ContextLayer,
    InputMeterUnverified,
)
from .inbox_cycle import InboxCycle
from .journal import Journal, JournalStep, input_fingerprint
from .loop_batch import ToolBatch
from .loop_codec import (
    ObservedPort,
    assistant_from,
    assistant_output,
    extend_aliases,
    verified_versions,
)
from .loop_policy import LoopPolicy, LoopStopped, RunControl
from .toolkit import ToolRegistry

FALLBACK = "这次还没整理出完整回答，请稍后继续。"


@dataclass(frozen=True)
class LoopOutcome:
    text: str
    asked: dict[str, Any] | None = field(repr=False)
    receipts: tuple[dict[str, Any], ...] = field(repr=False)
    alias_map: dict[str, dict[str, Any]] = field(repr=False)
    versions: dict[str, int] = field(repr=False)
    usage: dict[str, Any]
    stop_reason: str


class LoopCycle:
    """One traversal requires a fresh Journal; every provider step uses the frozen prefix."""

    def __init__(
        self,
        port: ModelPort,
        registry: ToolRegistry,
        journal: Journal,
        run: Mapping[str, Any],
        frozen: ContextBuild,
        *,
        policy: LoopPolicy | None = None,
        token_meter: TokenMeter | None = None,
        offline: bool = False,
        control: RunControl | None = None,
        budget_policy: BudgetPolicy | None = None,
        crisis: bool = False,
        incognito: bool = False,
        ledger: RequestLedger | None = None,
        emit: Callable[[str, dict[str, Any]], None] | None = None,
        tool_emit: Callable[[JournalStep, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.port, self.registry, self.journal, self.run, self.frozen = (
            port,
            registry,
            journal,
            dict(run),
            copy.deepcopy(frozen),
        )
        self.policy, self.token_meter, self.offline = policy or LoopPolicy(), token_meter, offline
        self.control = control or RunControl(registry.service.repo, run, self.policy)
        self.budget_policy, self.crisis, self.incognito = budget_policy or BudgetPolicy(), crisis, incognito
        self.ledger, self.emit, self.revising, self.revised = ledger, emit, False, False
        self.tool_emit = tool_emit
        self.cycle = f"{run['id']}:e{run['retry_epoch']}"
        self.messages: list[ChatMessage] = []
        self.aliases, self.versions = copy.deepcopy(frozen.alias_map), copy.deepcopy(frozen.injected_versions)
        self.receipts: list[dict[str, Any]] = []
        self.repeats: dict[str, int] = {}
        self.exposed: set[str] = set()
        self.usage: dict[str, Any] = {
            "model_steps": 0,
            "model_streams_this_execution": 0,
            "replayed_model_steps": 0,
            "reported_tokens": {},
            "offline": offline,
        }
        self.used, self.text, self.partial, self.asked = False, "", "", None
        self.last_step: JournalStep | None = None
        self.current_sources = tuple(run["request"].get("source_message_ids", [run["request"]["source_message_id"]]))
        self.inbox = InboxCycle(registry.service.repo)

    def _context(self, step: JournalStep | None = None) -> ToolContext:
        if step is not None:
            return ToolContext.from_step(
                step,
                thread_id=thread_id(self.run),
                source_ids=self.current_sources,
                case_ids=tuple(self.run["request"].get("case_ids", [])),
                source_versions=self.frozen.injected_versions,
                crisis=self.crisis,
                incognito=self.incognito,
            )
        return ToolContext(
            self.run["owner"],
            self.run["id"],
            self.run["subject"],
            self.run["retry_epoch"],
            1,
            self.run["lease_token"],
            "model",
            "0" * 64,
            thread_id(self.run),
            source_ids=self.current_sources,
            case_ids=tuple(self.run["request"].get("case_ids", [])),
            source_versions=self.frozen.injected_versions,
            crisis=self.crisis,
            incognito=self.incognito,
        )

    def _budget(self) -> Any:
        if self.token_meter is None:
            raise InputMeterUnverified()
        if self.offline and (
            getattr(self.port, "offline", False) is not True
            or self.token_meter.provider != "scripted"
            or self.token_meter.live_admissible is not False
        ):
            raise InputMeterUnverified()
        if any(layer.name == "CYCLE" and layer.items for layer in self.frozen.budget.layers):
            raise ContextInputError("loop_initial_cycle_not_empty")
        base = tuple(layer for layer in self.frozen.budget.layers if layer.name != "CYCLE")
        if any(
            message.reasoning or message.reasoning_signature or message.tool_calls or message.tool_cycle
            for layer in base
            for item in layer.items
            for message in item.messages
        ):
            raise ContextInputError("loop_prior_reasoning_not_allowed")
        tools = self.registry.specs(
            self._context(),
            required=(self.policy.only_tool,) if self.policy.only_tool and self.usage["model_steps"] == 0 else (),
        )
        if self.policy.text_only:
            tools = []
        required = self.policy.only_tool if self.usage["model_steps"] == 0 else None
        if required:
            tools = [tool for tool in tools if tool.name == required]
            if len(tools) != 1:
                raise EvidenceError("本步要求的工具当前不可用")
        choice = "required" if required else "auto"
        cycle = ContextLayer(
            "CYCLE",
            tuple(ContextItem(f"cycle:{index}", (message,), True) for index, message in enumerate(self.messages)),
        )
        meter = self.ledger.meter(self.run) if self.ledger else self.token_meter
        result = apply_token_budget(
            (*base, cycle), tuple(tools), meter=meter, policy=self.budget_policy, tool_choice=choice
        )
        if not self.offline:
            assert_live_allowed(result)
        return result, choice

    def _text_delta(self, text: str) -> None:
        self.partial += text
        self.control.note_text(text)
        if self.emit and not self.revising and text:
            self.emit("text_delta", {"text": text})

    def _model(self) -> Any:
        with confirmed(only_core=True):
            return self._model_step()

    def _model_step(self) -> Any:
        self.control.poll()
        name = "revision" if self.revising else ""
        restored = self.ledger.restore_next(self.journal, self.run, role="primary", name=name) if self.ledger else None
        self.inbox.prepare(self, restored)
        budget, choice = (restored.budget, restored.choice) if restored else self._budget()
        versions = restored.versions if restored else self.versions
        self.exposed = {tool.name for tool in budget.tools}
        identity = {
            "messages": [asdict(message) for message in budget.messages],
            "tools": [asdict(tool) for tool in budget.tools],
            "tool_choice": choice,
            "source_versions": versions,
        }
        step = self.journal.next_or_replay(
            self.run, kind="model", name=name, input_fp=input_fingerprint("model", name, identity)
        )
        if step.completed:
            response = assistant_from(step.output or {})
            self.usage["replayed_model_steps"] += 1
            if self.ledger:
                self.ledger.completed(step)
        else:
            self.partial = ""
            self.usage["model_streams_this_execution"] += 1
            if self.ledger:
                self.ledger.reserve(step, self.frozen, budget, choice, versions)
            from contextlib import nullcontext

            with self.ledger.physical(step) if self.ledger else nullcontext(), self.control.monitor():
                response = ObservedPort(self.port, self.control, self._text_delta).complete(
                    list(budget.messages),
                    tools=list(budget.tools),
                    tool_choice=choice,
                    cancel_event=self.control.cancel_event,
                )
            used_ids = {call.id for message in self.messages for call in message.tool_calls}
            if (choice == "required" and not response.tool_calls) or any(
                call.id in used_ids for call in response.tool_calls
            ):
                raise ModelProtocolError()
            completed = self.journal.complete(step, assistant_output(response), response.usage)
            if self.ledger:
                self.ledger.completed(completed)
            step = completed
        self.last_step = step
        self.inbox.completed(self, step)
        self.usage["model_steps"] += 1
        for key, value in response.usage.items():
            if type(value) is int and value >= 0:
                self.usage["reported_tokens"][key] = self.usage["reported_tokens"].get(key, 0) + value
        if response.text.strip():
            self.text = response.text
        self.messages.append(response.as_chat(tool_cycle=self.cycle))
        return response

    def _register(self, name: str, result: ToolResult) -> None:
        repo, owner = self.registry.service.repo, self.run["owner"]
        with repo.transaction(owner) as connection:
            current = self.journal._leased(connection, self.run)
            additions, records = verified_versions(self.registry.service, self.run, name, result)
            versions = reconcile_versions(repo, current, current["state_version"])
            for key, value in additions.items():
                if key in versions and versions[key] != value:
                    raise RevisionConflict("工具依赖变化缺少本轮精确写入证明")
                versions[key] = value
            repo.set_run_dependencies(owner, self.run["id"], versions, self.run["lease_token"])
            self.versions = versions
            extend_aliases(self.aliases, records)

    def _tool(self, call: ToolCall, ended: bool) -> tuple[ToolResult, str | None]:
        return ToolBatch(self).serial(call, ended)

    def revise(self, instructions: str) -> LoopOutcome:
        if not self.used or self.revised or not isinstance(instructions, str) or not instructions.strip():
            raise EvidenceError("评审改写最多执行一次且需要受信意见")
        self.revised, self.revising = True, True
        self.messages.append(ChatMessage("system", instructions))
        self.policy = replace(self.policy, text_only=True, only_tool=None)
        response = self._model()
        if response.tool_calls or not response.text.strip():
            raise ModelProtocolError()
        self.revising = False
        return self._outcome("revised")

    def _outcome(self, reason: str) -> LoopOutcome:
        text = self.text or self.partial or (self.asked or {}).get("question") or FALLBACK
        return LoopOutcome(
            text,
            copy.deepcopy(self.asked),
            tuple(copy.deepcopy(self.receipts)),
            copy.deepcopy(self.aliases),
            dict(self.versions),
            copy.deepcopy(self.usage),
            reason,
        )

    def execute(self) -> LoopOutcome:
        if self.used:
            raise EvidenceError("循环实例不可复用，请创建新的步骤日志遍历")
        self.used = True
        try:
            for _ in range(self.policy.iterations):
                response = self._model()
                if not response.tool_calls:
                    return self._outcome("completed" if response.text.strip() else "empty_answer")
                if len(response.tool_calls) > self.policy.tools_per_step:
                    return self._outcome("step_tool_limit")
                ended, stopped = ToolBatch(self).execute(response.tool_calls)
                if ended or stopped:
                    return self._outcome("asked" if ended else stopped or "tool_stop")
            return self._outcome("iteration_limit")
        except LoopStopped as error:
            return self._outcome(error.reason)
        except ModelAttemptUnconfirmed:
            raise
        except ModelUnavailable as error:
            return self._outcome(error.code.lower())
        except CoreError:
            return self._outcome("lease_or_dependency_invalid")

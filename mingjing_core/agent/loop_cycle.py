"""Recoverable model/tool cycle only; RuntimePort, final commit and events are separate."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import ValidationError

from mingjing_core.application.agent_commit_versions import reconcile_versions
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.domain.contracts import CoreError, EvidenceError, RevisionConflict
from mingjing_core.models.errors import ModelProtocolError, ModelUnavailable
from mingjing_core.models.port import ChatMessage, ModelPort, ToolCall

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
from .journal import Journal, JournalStep, input_fingerprint
from .loop_codec import ObservedPort, assistant_from, assistant_output, extend_aliases, tool_message, verified_versions
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

    def _context(self, step: JournalStep | None = None) -> ToolContext:
        if step is not None:
            return ToolContext.from_step(
                step,
                thread_id="life:" + self.run["subject"],
                source_ids=(self.run["request"]["source_message_id"],),
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
            "life:" + self.run["subject"],
            source_ids=(self.run["request"]["source_message_id"],),
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
        tools = self.registry.specs(self._context())
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
        result = apply_token_budget(
            (*base, cycle), tuple(tools), meter=self.token_meter, policy=self.budget_policy, tool_choice=choice
        )
        if not self.offline:
            assert_live_allowed(result)
        return result, choice

    def _text_delta(self, text: str) -> None:
        self.partial += text

    def _model(self) -> Any:
        self.control.poll()
        budget, choice = self._budget()
        self.exposed = {tool.name for tool in budget.tools}
        identity = {
            "messages": [asdict(message) for message in budget.messages],
            "tools": [asdict(tool) for tool in budget.tools],
            "tool_choice": choice,
            "source_versions": self.frozen.injected_versions,
        }
        step = self.journal.next_or_replay(self.run, kind="model", input_fp=input_fingerprint("model", "", identity))
        if step.completed:
            response = assistant_from(step.output or {})
            self.usage["replayed_model_steps"] += 1
        else:
            self.partial = ""
            self.usage["model_streams_this_execution"] += 1
            with self.control.monitor():
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
            self.journal.complete(step, assistant_output(response), response.usage)
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
        self.control.poll()
        failure = None
        try:
            fingerprint = self.registry.fingerprint(
                call.name, call.arguments, source_versions=self.frozen.injected_versions
            )
        except (ValidationError, ValueError, KeyError):
            fingerprint = input_fingerprint(
                "tool", call.name, {"arguments": call.arguments, "source_versions": self.frozen.injected_versions}
            )
            failure = "invalid_tool_request"
        if call.name not in self.exposed:
            failure = "tool_unavailable"
        self.repeats[fingerprint] = self.repeats.get(fingerprint, 0) + 1
        repeated = self.repeats[fingerprint] >= self.policy.repeat_limit
        step = self.journal.next_or_replay(self.run, kind="tool", name=call.name, input_fp=fingerprint)
        if step.completed:
            result = ToolResult.model_validate(step.output)
        else:
            code = "turn_ended" if ended else "repeated_tool" if repeated else failure
            if code:
                result = ToolResult(ok=False, data={"code": code}, summary="本次工具未执行")
            else:
                result = self.registry.execute(call.name, call.arguments, self._context(step))
            self.journal.complete(step, result.model_dump())
        self._register(call.name, result)
        if result.receipt:
            self.receipts.append(copy.deepcopy(result.receipt))
        if result.ends_turn:
            self.asked = copy.deepcopy(result.data.get("asked"))
        self.messages.append(tool_message(call.id, result, self.cycle))
        return result, "repeated_tool" if repeated and not ended else None

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
                ended, stopped = False, None
                for call in response.tool_calls:
                    result, reason = self._tool(call, ended or stopped is not None)
                    ended, stopped = ended or result.ends_turn, stopped or reason
                if ended or stopped:
                    return self._outcome("asked" if ended else stopped or "tool_stop")
            return self._outcome("iteration_limit")
        except LoopStopped as error:
            return self._outcome(error.reason)
        except ModelUnavailable as error:
            return self._outcome(error.code.lower())
        except CoreError:
            return self._outcome("lease_or_dependency_invalid")

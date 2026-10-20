"""A separately callable PostgreSQL context prototype with no model transport."""

from __future__ import annotations

from collections.abc import Mapping

from mingjing_core.application.context_epochs import ContextEpochService
from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import ChatMessage, ToolSpec
from mingjing_core.timekit.clock import Clock, get_clock

from .context_budget import apply_budget
from .context_dependencies import injected_versions
from .context_layers import build_layers
from .context_sources import BoundedSources
from .context_tokens import TokenMeter, apply_token_budget
from .context_types import (
    BudgetPolicy,
    ContextBuild,
    ContextInputError,
    ContextItem,
    ContextLayer,
    SourceSnapshot,
)


class ContextEngine:
    def __init__(
        self,
        memory: MemoryService,
        system_text: str,
        *,
        clock: Clock | None = None,
        policy: BudgetPolicy | None = None,
        token_meter: TokenMeter | None = None,
    ) -> None:
        if not isinstance(system_text, str) or not system_text.strip():
            raise ContextInputError("context_system_required")
        self.memory, self.system_text = memory, system_text
        self.clock, self.policy = clock or get_clock(), policy or BudgetPolicy()
        self.token_meter = token_meter

    def _layers(self, snapshot: SourceSnapshot) -> tuple[list[ContextLayer], dict[str, dict[str, str | int]]]:
        return build_layers(snapshot, self.system_text, self.clock, self.policy)

    def build(
        self,
        owner: str,
        source_message_id: str,
        *,
        subject: str = "self",
        thread_id: str | None = None,
        case_ids: tuple[str, ...] = (),
        tools: tuple[ToolSpec, ...] = (),
        current_epoch_messages: tuple[ChatMessage, ...] = (),
        tool_summaries: Mapping[str, str] | None = None,
        query: str | None = None,
        tool_choice: str = "auto",
        run_context: dict | None = None,
    ) -> ContextBuild:
        if self.clock is not get_clock():
            raise ContextInputError("context_clock_mismatch")
        if any(message.role not in {"assistant", "tool"} for message in current_epoch_messages):
            raise ContextInputError("context_cycle_source_invalid")
        tags = {message.tool_cycle for message in current_epoch_messages}
        if current_epoch_messages and (len(tags) != 1 or not isinstance(next(iter(tags)), str) or not next(iter(tags))):
            raise ContextInputError("context_cycle_invalid")
        if thread_id and thread_id.startswith("incognito:"):
            from .context_private import private_sources

            if case_ids:
                raise ContextInputError("private_context_cases_not_allowed")
            snapshot = private_sources(
                self.memory, owner, subject, thread_id, source_message_id, self.policy, run_context=run_context
            )
        else:
            snapshot = self._sources(owner, subject, source_message_id, thread_id, case_ids, query, run_context)
        return self._assemble(snapshot, tools, current_epoch_messages, tool_summaries or {}, tool_choice)

    def _sources(self, owner, subject, source_message_id, thread_id, case_ids, query, run_context) -> SourceSnapshot:
        return BoundedSources(self.memory, self.policy, run_context=run_context).read(
            owner,
            subject,
            source_message_id,
            thread_id=thread_id or "life:" + subject,
            case_ids=case_ids,
            query=query,
        )

    def _assemble(
        self,
        snapshot: SourceSnapshot,
        tools: tuple[ToolSpec, ...],
        current_epoch_messages: tuple[ChatMessage, ...],
        tool_summaries: Mapping[str, str],
        tool_choice: str,
    ) -> ContextBuild:
        layers, aliases = self._layers(snapshot)
        cycle = tuple(
            ContextItem(
                "cycle:" + str(index),
                (message,),
                True,
                tool_summaries.get(message.tool_call_id or ""),
            )
            for index, message in enumerate(current_epoch_messages)
        )
        layers.append(ContextLayer("CYCLE", cycle))
        if self.token_meter is None:
            budget = apply_budget(tuple(layers), tools, policy=self.policy, tool_choice=tool_choice)
        else:
            budget = apply_token_budget(
                tuple(layers),
                tools,
                policy=self.policy,
                meter=self.token_meter,
                tool_choice=tool_choice,
            )
        retained = {ident for layer in budget.layers for item in layer.items for ident in (item.key, *item.source_ids)}
        aliases = {key: value for key, value in aliases.items() if value["id"] in retained}
        versions = injected_versions(snapshot, budget)
        cache_epoch = ContextEpochService(self.memory.repo).preview(
            snapshot.owner, snapshot.subject, snapshot.current["thread_id"], budget, versions, snapshot.revision
        )
        limitations = ("runtime_unconnected",)
        if not budget.meter.live_admissible:
            limitations += ("provider_framing_unverified",)
        if self.token_meter is None:
            limitations += ("offline_policy_units",)
        if budget.meter.token_meter_version == "public_k3_estimate_v1":
            limitations += ("estimated_input_bound",)
        return ContextBuild(
            budget,
            snapshot.revision,
            aliases,
            versions,
            snapshot.read_counts,
            limitations,
            cache_epoch,
        )

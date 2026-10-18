"""A separately callable PostgreSQL context prototype with no model transport."""

from __future__ import annotations

import json
from collections.abc import Mapping

from mingjing_core.application.memory import MemoryService
from mingjing_core.models.port import ChatMessage, ToolSpec
from mingjing_core.timekit.clock import Clock, get_clock
from mingjing_core.timekit.now_block import render_now_block

from .context_budget import apply_budget
from .context_sources import BoundedSources
from .context_types import BudgetPolicy, ContextBuild, ContextInputError, ContextItem, ContextLayer, SourceSnapshot


class ContextEngine:
    def __init__(
        self,
        memory: MemoryService,
        system_text: str,
        *,
        clock: Clock | None = None,
        policy: BudgetPolicy | None = None,
    ) -> None:
        if not isinstance(system_text, str) or not system_text.strip():
            raise ContextInputError("context_system_required")
        self.memory, self.system_text = memory, system_text
        self.clock, self.policy = clock or get_clock(), policy or BudgetPolicy()

    def _layers(self, snapshot: SourceSnapshot) -> tuple[list[ContextLayer], dict[str, dict[str, str | int]]]:
        aliases: dict[str, dict[str, str | int]] = {}
        facts = sorted(snapshot.facts, key=lambda row: (row.get("kind") != "constraint", row["id"]))
        fact_items = []
        for index, fact in enumerate(facts, 1):
            alias = "f" + str(index)
            aliases[alias] = {"kind": "fact", "id": fact["id"], "revision": fact["revision"]}
            content = json.dumps(
                {"alias": alias, "date": fact.get("valid_from"), "kind": fact["kind"], "text": fact["content"]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            fact_items.append(ContextItem(fact["id"], (ChatMessage("system", "<画像>" + content + "</画像>"),), True))
        history_items = self._history(snapshot, aliases)
        memories = self._memories(snapshot, aliases)
        previous = next((row for row in reversed(snapshot.history) if row.get("role") == "user"), None)
        now = render_now_block(snapshot.settings, self.clock, previous, snapshot.facts)
        layers = [
            ContextLayer("L0", (ContextItem("system", (ChatMessage("system", self.system_text),), True),)),
            ContextLayer("L2", tuple(fact_items)),
            ContextLayer("L5", tuple(history_items)),
            ContextLayer("L4", tuple(memories)),
            ContextLayer("L1", (ContextItem("now", (ChatMessage("system", now),), True),)),
            ContextLayer(
                "L6", (ContextItem(snapshot.current["id"], (ChatMessage("user", snapshot.current["content"]),), True),)
            ),
        ]
        return layers, aliases

    def _history(self, snapshot: SourceSnapshot, aliases: dict[str, dict[str, str | int]]) -> list[ContextItem]:
        groups: list[ContextItem] = []
        for row in snapshot.history:
            role = row.get("role")
            if role not in {"user", "assistant"} or role == "assistant" and not groups:
                continue
            alias = "m" + str(len(aliases) + 1)
            aliases[alias] = {"kind": "message", "id": row["id"], "revision": row["revision"]}
            content = f"〔{alias}〕 [{row.get('at', '')} {row.get('channel', '')}]\n{row['content']}"
            message = ChatMessage(role, content)
            if role == "assistant":
                old = groups[-1]
                groups[-1] = ContextItem(old.key, (*old.messages, message), source_ids=(*old.source_ids, row["id"]))
            else:
                groups.append(ContextItem(row["id"], (message,), source_ids=(row["id"],)))
        return groups

    def _memories(self, snapshot: SourceSnapshot, aliases: dict[str, dict[str, str | int]]) -> list[ContextItem]:
        items = []
        for row in snapshot.retrieved:
            alias = "m" + str(len(aliases) + 1)
            aliases[alias] = {"kind": "message", "id": row["id"], "revision": row["revision"]}
            value = {
                "alias": alias,
                "date": row.get("at"),
                "kind": "message",
                "valid": True,
                "source": "明镜（我之前说的）" if row.get("role") == "assistant" else row.get("channel"),
                "text": row["content"],
            }
            content = "<相关记忆>\n" + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n</相关记忆>"
            items.append(ContextItem(row["id"], (ChatMessage("system", content),)))
        return items

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
    ) -> ContextBuild:
        if self.clock is not get_clock():
            raise ContextInputError("context_clock_mismatch")
        if any(message.role not in {"assistant", "tool"} for message in current_epoch_messages):
            raise ContextInputError("context_cycle_source_invalid")
        tags = {message.tool_cycle for message in current_epoch_messages}
        if current_epoch_messages and (len(tags) != 1 or not isinstance(next(iter(tags)), str) or not next(iter(tags))):
            raise ContextInputError("context_cycle_invalid")
        snapshot = BoundedSources(self.memory, self.policy).read(
            owner, subject, source_message_id, thread_id=thread_id or "life:" + subject, case_ids=case_ids, query=query
        )
        layers, aliases = self._layers(snapshot)
        cycle = tuple(
            ContextItem("cycle:" + str(index), (message,), True, (tool_summaries or {}).get(message.tool_call_id or ""))
            for index, message in enumerate(current_epoch_messages)
        )
        layers.append(ContextLayer("CYCLE", cycle))
        budget = apply_budget(tuple(layers), tools, policy=self.policy, tool_choice=tool_choice)
        retained = {ident for layer in budget.layers for item in layer.items for ident in (item.key, *item.source_ids)}
        aliases = {key: value for key, value in aliases.items() if value["id"] in retained}
        versions = dict(snapshot.versions)
        # Dependency precision and a send-time revocation gate belong to the runtime milestone.
        return ContextBuild(budget, snapshot.revision, aliases, versions, snapshot.read_counts)

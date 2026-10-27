"""A real ToolBatch effect/ack with a still-running PG run, without a model call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mingjing_core.agent.loop_batch import PreparedTool, ToolBatch
from mingjing_core.agent.loop_cycle import LoopCycle
from mingjing_core.application.agent_memory_receipts import MemoryReceiptEvents
from mingjing_core.application.agent_runtime_events import RuntimeEvents
from mingjing_core.application.agent_tools_contracts import ToolResult
from mingjing_core.models.port import ToolCall
from mingjing_core.repositories.postgres import PostgresRepository
from tests.v4.agent.test_loop_cycle_support import ScriptedPort, cycle, prepare, writer


@dataclass
class ReceiptCase:
    repo: PostgresRepository
    cycle: LoopCycle
    prepared: PreparedTool
    result: ToolResult
    hook: MemoryReceiptEvents
    observed: list[dict]

    def record(self) -> dict | None:
        with self.repo.transaction("alice"):
            return self.hook.record(
                self.prepared.step,
                self.result,
                arguments=self.prepared.call.arguments,
                context=self.prepared.context,
            )


def make_case(
    repo: PostgresRepository,
    *,
    text: str = "我喜欢合成夜班",
    name: str = "memory_write",
    arguments: Callable[[dict], dict] = writer,
    acknowledge: bool = True,
) -> ReceiptCase:
    run, registry, frozen = prepare(repo, text)
    component = cycle(ScriptedPort([]), registry, run, frozen)
    component.exposed = {spec.name for spec in registry.specs(component._context())}
    batch = ToolBatch(component)
    prepared = batch.prepare(ToolCall("synthetic_memory_call", name, arguments(run)), False)
    result = batch.invoke(prepared)
    if acknowledge:
        with repo.transaction("alice"):
            component.journal.complete(prepared.step, result.model_dump())
            component._register(name, result)
    observed: list[dict[str, Any]] = []
    hook = MemoryReceiptEvents(RuntimeEvents(repo, run, observed.append))
    return ReceiptCase(repo, component, prepared, result, hook, observed)

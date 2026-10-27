"""Record in the acknowledgement transaction; deliver only after its real commit."""

from __future__ import annotations

import copy
from typing import Any

from psycopg import sql

from mingjing_core.agent.journal import JournalStep
from mingjing_core.application import agent_runtime_events
from mingjing_core.application.agent_memory_receipt_proof import project_receipt
from mingjing_core.application.agent_tools_contracts import ToolContext, ToolResult
from mingjing_core.domain.contracts import EvidenceError


class MemoryReceiptEvents:
    def __init__(self, events: agent_runtime_events.RuntimeEvents) -> None:
        self.events = events

    def check_boundary(self) -> None:
        if getattr(self.events.repo._local, "connection", None) is not None:
            raise EvidenceError("记忆回执确认不能加入已有外层事务")

    def record(self, step: JournalStep, result: ToolResult, *, arguments: dict, context: ToolContext) -> dict | None:
        repo, run = self.events.repo, self.events.run
        connection = getattr(repo._local, "connection", None)
        if connection is None:
            raise EvidenceError("记忆回执必须与工具确认在同一事务记录")
        payload = project_receipt(repo, connection, run, step, result, arguments, context)
        if payload is None:
            return None
        key = f"memory_receipt:v1:s{step.seq}:{step.input_fp}"
        operation = f"p4-event:{run['id']}:e{run['retry_epoch']}:{key}"
        prior = connection.execute(
            sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND operation_id=%s").format(repo.table("core_operations")),
            (run["owner"], operation),
        ).fetchone()
        event = agent_runtime_events.append_event(repo, connection, run, "memory_receipt", payload, operation_key=key)
        return None if prior else event

    def dispatch(self, event: dict[str, Any] | None) -> None:
        self.check_boundary()
        if event is not None and self.events.callback is not None:
            try:
                self.events.callback(copy.deepcopy(event))
            except Exception:
                # A client callback cannot undo an acknowledged durable memory effect.
                return

"""One synthetic external withdrawal after a real frozen context; no runtime gates are replaced."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.application.memory import MemoryService
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.port import ChatMessage, StreamEvent

from .v4_faults import FaultScriptedPort


class MemoryRevocationPort(FaultScriptedPort):
    def __init__(self, target: Any) -> None:
        super().__init__()
        self.target, self.fired, self.revoked_id = target, False, None

    def stream(self, messages: list[ChatMessage], **kwargs: Any) -> Iterator[StreamEvent]:
        if not self.fired:
            target = self.target
            label = target.seed["controls"]["revoke_after_context"]
            ident = target.seeder.ids[label]
            fact = target.repo.get(target.owner, "fact", ident)
            run = target.repo.fetch_run(target.owner, target.run_ids[-1])
            if run["state_version"].get("fact:" + ident) != fact["revision"]:
                raise ValueError("Late withdrawal must target a fact actually frozen into this runtime context")
            self.fired, self.revoked_id = True, ident
            MemoryService(target.repo).retire_fact(target.owner, ident, expected_revision=fact["revision"])
            # Simulate the source barrier discovering concurrent withdrawal before
            # returning a private draft; AgentRuntime must perform its own restart.
            raise EvidenceError("合成并发撤销，当前上下文已经失效")
        yield from super().stream(messages, **kwargs)


def regeneration_observations(target: Any, run: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(target.port, MemoryRevocationPort) or not target.port.fired:
        return []
    meta = run.get("usage", {}).get("agent_runtime", {})
    ident = target.port.revoked_id
    if (
        run["status"] != "succeeded"
        or run["retry_epoch"] != 1
        or meta.get("regenerations") != 1
        or not target.repo.is_revoked(target.owner, "fact", ident)
        or "fact:" + ident in run.get("state_version", {})
    ):
        return []
    return [
        {
            "name": name,
            "source_store": "core_runs retry_epoch/usage + core_revocations",
            "run_id": run["id"],
            "epoch": run["retry_epoch"],
            "rule": "actual one-epoch restart after real frozen fact withdrawal; evaluator-only",
        }
        for name in ("context.invalidated", "run.regenerated")
    ]


def queue_memory_revoke_turn(target: Any, turn: dict[str, Any]) -> dict[str, Any]:
    # Normal intake preserves the exact request proof used by AgentRegenerator.
    # Rewriting a raw queue_run fingerprint would bypass the behavior under test.
    with target.repo.transaction(target.owner) as connection:
        settings = dict(target.repo.assert_scope(target.owner)["settings"], runtime="v4")
        connection.execute(
            sql.SQL("UPDATE {} SET settings=%s WHERE id=%s").format(target.repo.table("core_owners")),
            (Jsonb(settings), target.owner),
        )
    run = ThreadIngress(target.service).submit(
        owner=target.owner,
        thread_id=target.thread["id"],
        message=turn["user"],
        request_id=f"v4-eval:{target.seed['_scenario_id']}:{turn['_index']}",
        depth="standard",
    )
    target.bindings[f"turn-{turn['_index']}"] = run["request"]["source_message_id"]
    return target.repo.claim_run(target.owner, run["id"], lease_seconds=150)

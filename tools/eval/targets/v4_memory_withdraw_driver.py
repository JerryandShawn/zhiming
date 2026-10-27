"""Selected memory actions use authenticated local originals and actual privacy services."""

from __future__ import annotations

import time
from typing import Any

from mingjing_core.application.memory2_withdrawals import MemoryWithdrawalService
from mingjing_core.application.threads import ThreadService

from .base import TurnResult
from .v4_memory_privacy_views import native_counts
from .v4_privacy_observations import erased


class MemoryWithdrawDriver:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.original_revisions: dict[tuple[str, str], int] = {}

    def _linked(self, kind, ident):
        if kind != "fact":
            return []
        return [
            item["id"]
            for item in self.target.repo.list(self.target.owner, "followup", include_deleted=True)
            if item.get("source_fact_id") == ident
            or ident in set(item.get("fact_ids", [])) | set(item.get("used_fact_ids", []))
        ]

    def _history(self, turn, kind, ident, linked, receipt):
        target = self.target
        current = target.repo.get(target.owner, kind, ident, include_deleted=True)
        effects = [kind + " " + ident + " → " + current["status"]]
        for followup_id in linked:
            row = target.repo.get(target.owner, "followup", followup_id, include_deleted=True)
            state = row["status"]
            if (
                state == "deleted"
                and target.repo.is_revoked(target.owner, "fact", ident)
                and erased(target.repo, target.owner, "followup", followup_id)
            ):
                state = "cancelled (native_status=deleted)"
            effects.append("followup " + followup_id + " → " + state)
        entry = {"turn": turn["_index"], "user_gist": turn["user"][:60], "receipts": [receipt], "effects": effects}
        prior = next((row for row in target.judge_action_history if row["turn"] == turn["_index"]), None)
        if prior is None:
            target.judge_action_history.append(entry)
        elif prior != entry:
            raise ValueError("Native withdrawal history changed before replay")
        return {"memories": [receipt], "effects": effects}

    def send(self, turn: dict[str, Any]) -> TurnResult:
        started, target = time.perf_counter(), self.target
        action = turn["action"]
        kind = "message" if action["type"] == "source_delete" else "fact"
        label = action["message_id"] if kind == "message" else action["fact_id"]
        ident = target.bindings.get(label)
        if ident is None:
            raise ValueError("Withdrawal must select an actual declared source or fact")
        row = target.repo.get(target.owner, kind, ident, include_deleted=True)
        linked = self._linked(kind, ident)
        revision = self.original_revisions.setdefault((kind, ident), row["revision"])
        operation = f"memory-withdraw:{target.seed['_scenario_id']}:{turn['_index']}"
        source = ThreadService(target.repo).receive(
            target.owner, target.thread["id"], turn["user"], request_id=operation, channel="web-action"
        )
        service = MemoryWithdrawalService(target.service.memory)
        method = service.delete_source if kind == "message" else service.withdraw_fact
        receipt = method(
            target.owner, "self", ident, expected_revision=revision, message_id=source["id"], operation_id=operation
        )
        target.bindings[f"turn-{turn['_index']}"] = source["id"]
        after = native_counts(target.privacy_seed)
        observations = [
            {
                "name": "source.deleted" if kind == "message" else "memory.fact_revoked",
                "source_store": "core_entities + core_revocations",
                "id": ident,
                "rule": "actual authenticated selected-item withdrawal; evaluator-only",
            }
        ]
        if kind == "message" and target.privacy_seed.baseline and all(value == 0 for value in after.values()):
            observations.append(
                {
                    "name": "derived.invalidated",
                    "source_store": "native dependency/embedding/run stores",
                    "before": target.privacy_seed.baseline,
                    "after": after,
                    "rule": "nonempty initial native layers cleared; evaluator-only",
                }
            )
        target.semantic, target.semantic_history = observations, target.semantic_history + observations
        effects = self._history(turn, kind, ident, linked, receipt)
        return TurnResult(
            receipts=[receipt],
            events=[r["name"] for r in observations],
            model_calls=0,
            elapsed_seconds=time.perf_counter() - started,
            metadata={
                "offline": True,
                "physical_model_requests": 0,
                "evaluator_observations": observations,
                "tool_effects": effects,
            },
        )

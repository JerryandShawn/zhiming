"""Offline memory actions call real services; observations are never public SSE events."""

from __future__ import annotations

import time
from typing import Any

from psycopg import sql

from mingjing_core.application.memory2_proposals import MemoryProposalService
from mingjing_core.application.threads import ThreadService
from tools.eval.providers.scripted import ScriptedProvider

from .base import TurnResult
from .v4_memory_history_seed import declared_reply, execute_historical, pending_source_label


class MemoryActionDriver:
    def __init__(self, target: Any) -> None:
        self.target = target
        self.ids: dict[str, str] = {}
        self.revisions: dict[str, int] = {}
        self.setup_calls = 0

    def seed(self) -> None:
        target = self.target
        for fixture in target.seed.get("entities", []):
            label = pending_source_label(target.seed, fixture)
            if label is None:
                continue
            source_id = target.seeder.ids[label]
            reply = declared_reply(target.seed, label)
            source = target.service.memory.get_source(target.owner, source_id)
            run = self._queue(source, fixture["id"])
            args = {
                "message_id": source_id,
                "quote": source["content"],
                "summary": source["content"],
                "kind": "background",
                "sensitivity": fixture["data"]["sensitivity"],
            }
            provider = ScriptedProvider(
                [
                    {
                        "turn": 1,
                        "model": [
                            {"tool_call": {"name": "memory_write", "arguments": args}},
                            {"text": reply["content"] if reply is not None else "这条敏感记忆需要你确认后才保存。"},
                        ],
                    }
                ]
            )
            before = target.port.calls
            result = execute_historical(target, run, provider, reply)
            if reply is not None:
                self.ids[reply["id"]] = result["message_id"]
                target.seeder.ids[reply["id"]] = result["message_id"]
            self.setup_calls += target.port.calls - before
            from .v4_observations import tool_steps

            receipts = [s["output"].get("receipt", {}) for s in tool_steps(target.repo, target.owner, run["id"])]
            proposals = [r["id"] for r in receipts if r.get("write_status") == "pending_confirmation"]
            if len(proposals) != 1:
                raise ValueError("Memory seed must produce exactly one actual pending P3 proposal")
            self.ids[fixture["id"]] = proposals[0]
            self.revisions[fixture["id"]] = target.repo.get(target.owner, "proposal", proposals[0])["revision"]
            target.run_ids.append(run["id"])
            self._register_native_layer(fixture, source_id, proposals[0], reply, result)

    def _register_native_layer(
        self, fixture: dict, source_id: str, proposal_id: str, reply: dict | None, result: dict
    ) -> None:
        target = self.target
        if target.seed.get("_scenario_id") not in {"F01", "F02", "F03"}:
            return
        target.seeder.privacy_layers.append(
            {
                "kind": "proposal",
                "id": fixture["id"],
                "sources": [source_id],
                "fact_id": None,
                "native_kind": "proposal",
                "actual_p3_pending": True,
                "native_id": proposal_id,
            }
        )
        target.seeder.ids[fixture["id"]] = proposal_id
        if reply is not None:
            target.seeder.privacy_aliases[result["message_id"]] = reply["id"]

    def _queue(self, source: dict[str, Any], label: str) -> dict[str, Any]:
        target = self.target
        if source.get("thread_id") != target.thread["id"] or source.get("role") != "user":
            raise ValueError("Synthetic memory setup source must belong to the actual owner thread")
        run = target.repo.queue_run(
            target.owner,
            "memory-seed:" + label,
            {
                "message": source["content"],
                "source_message_id": source["id"],
                "thread_id": target.thread["id"],
                "case_ids": [],
                "depth": "standard",
            },
        )
        with target.repo.transaction(target.owner) as connection:
            connection.execute(
                sql.SQL("UPDATE {} SET runtime='v4',thread_id=%s WHERE owner=%s AND id=%s").format(
                    target.repo.table("core_runs")
                ),
                (target.thread["id"], target.owner, run["id"]),
            )
        return target.repo.claim_run(target.owner, run["id"], lease_seconds=150)

    def accept(self, turn: dict[str, Any]) -> TurnResult:
        started, target = time.perf_counter(), self.target
        action = turn["action"]
        if action["proposal_id"] not in self.ids:
            raise ValueError("Memory action needs an actual source-backed proposal")
        ident = self.ids[action["proposal_id"]]
        proposal = target.repo.get(target.owner, "proposal", ident)
        if action.get("auto_save_category") != proposal.get("sensitivity"):
            raise ValueError("Consent category must match the selected actual proposal")
        operation = f"memory-action:{target.seed['_scenario_id']}:{turn['_index']}"
        source = ThreadService(target.repo).receive(
            target.owner, target.thread["id"], turn["user"], request_id=operation, channel="web-action"
        )
        receipt = MemoryProposalService(target.service.memory).accept(
            target.owner,
            "self",
            ident,
            expected_revision=self.revisions[action["proposal_id"]],
            message_id=source["id"],
            remember_category=True,
            operation_id=operation,
        )
        target.bindings[f"turn-{turn['_index']}"] = source["id"]
        fact = target.repo.get(target.owner, "fact", receipt["fact_id"])
        proof = target.repo.get(target.owner, "consent", fact["approval_consent_id"])
        settings = target.repo.assert_scope(target.owner)["settings"]
        if proof["status"] != "active" or action["auto_save_category"] not in settings.get("auto_save_categories", []):
            raise ValueError("Consent action did not persist actual category authority")
        observation = {
            "name": "consent.category_updated",
            "source_store": "core_owners.settings + consent/proposal",
            "proposal_id": ident,
            "consent_id": proof["id"],
            "rule": "actual authenticated service result; evaluator-only",
        }
        target.semantic = [observation]
        target.semantic_history.append(observation)
        return TurnResult(
            receipts=[receipt],
            events=[observation["name"]],
            model_calls=0,
            elapsed_seconds=time.perf_counter() - started,
            metadata={"offline": True, "physical_model_requests": 0, "evaluator_observations": [observation]},
        )

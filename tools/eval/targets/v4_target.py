"""Real v4 RuntimePort on a loopback PG15 schema, with scripted ModelPort only."""

from __future__ import annotations

import os
import re
import time
import uuid
from typing import Any

from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.repositories.postgres import ENTITY_KINDS, PostgresRepository
from tools.eval.providers.scripted import ScriptedProvider

from .base import TurnResult
from .local_db import local_dsn, verify_local_postgres
from .v4_cancellation import cancel_stream
from .v4_chart_observations import chart_observations
from .v4_context_observations import context_observations
from .v4_faults import FaultScriptedPort, crash_observations, reclaim_crashed
from .v4_feishu import FeishuBatchDriver
from .v4_http_faults import HttpFaultPort, fault_evidence, fault_port
from .v4_observations import (
    decision_rows,
    delivery_rows,
    local_entity,
    repeat_count,
    semantic_observations,
    structural_observations,
    tool_steps,
)
from .v4_privacy import NativePrivacyDriver
from .v4_privacy_observations import initial_layers, privacy_entities
from .v4_privacy_seed import V4PrivacySeeder
from .v4_protocols import ScriptedWirePort, run_matrix
from .v4_review_harness import critic_script, harness_evidence
from .v4_review_observations import review_observations
from .v4_run_observations import native_run_meta, native_run_rows
from .v4_runtime import EvaluationRuntime
from .v4_scripted import ForbiddenLegacyModel, ScriptedMeter, ScriptedModelPort
from .v4_sse_reconnect import reconnect
from .v4_tarot import TarotDriver
from .v4_tool_effects import previous_turns, tool_effects
from .v4_withdrawal import configure_withdrawal, regeneration_state, withdrawal_observations


class V4Target:
    def __init__(
        self,
        *,
        dsn: str | None = None,
        protocol: str | None = None,
        candidate: str = "scripted-v4",
    ) -> None:
        self.dsn = local_dsn(dsn or os.getenv("CORE_TEST_DSN", ""))
        self.owner = "synthetic-eval-owner"
        self.repo: PostgresRepository | None = None
        self.schema = ""
        self.seed: dict[str, Any] = {}
        self.bindings: dict[str, str] = {}
        self.run_ids: list[str] = []
        self.cancellation: dict[str, Any] = {}
        self.protocol, self.candidate, self.portability = protocol, candidate, {}
        self.semantic: list[dict[str, Any]] = []
        self.semantic_history: list[dict[str, Any]] = []
        self.crashed_run: str | None = None
        self.feishu: FeishuBatchDriver | None = None
        self.stream: dict[str, Any] = {}
        self.http_faults: HttpFaultPort | None = None

    def reset(self, seed: dict[str, Any]) -> None:
        if seed.get("synthetic") is not True:
            raise ValueError("v4 evaluation requires explicitly synthetic data")
        http_faults = fault_port(seed, self.protocol, scripted=type(self)._ports is V4Target._ports)
        self.close()
        verify_local_postgres(self.dsn)
        self.seed = seed
        self.http_faults = http_faults
        self.cancellation = {}
        self.portability = {}
        self.semantic = []
        self.semantic_history = []
        self.judge_action_history = []
        self.tool_visibility_history = []
        self.crashed_run = None
        self.feishu = None
        self.stream = {}
        self.schema = "eval_v4_" + uuid.uuid4().hex
        self.repo = PostgresRepository(self.dsn, schema=self.schema, max_size=4)
        self.repo.ensure_owner(
            self.owner,
            settings={"auto_save_low_sensitivity": True, **seed.get("settings", {}), "runtime": "v4"},
        )
        self._ports()
        self.service = ConsultationService(self.repo, model=ForbiddenLegacyModel(), runtime=self.runtime)
        self.provider = ScriptedProvider(seed.get("_scripted", []))
        self.seeder = V4PrivacySeeder(self.service, self.owner, seed.get("_scenario_id", "scenario"))
        self.seeder.seed(seed)
        self.privacy_initial = initial_layers(self.repo, self.owner, self.seeder.privacy_layers)
        self.tarot = TarotDriver(self.service, self.seeder)
        self.tarot.seed(seed)
        self.bindings = dict(self.seeder.ids)
        self.bindings.update(self.tarot.ids)
        self.thread = ThreadService(self.repo).create(
            self.owner, request_id="eval-thread", incognito=seed.get("incognito", False)
        )

    def _ports(self) -> None:
        controls = self.seed.get("controls", {})
        self.port = (
            self.http_faults
            if self.http_faults is not None
            else ScriptedWirePort(self.protocol, self.candidate)
            if self.protocol
            else FaultScriptedPort(crash_after_tool=controls.get("crash_after") == "tool_commit")
        )
        review_script = critic_script(self.seed)
        self.critic = ScriptedModelPort() if review_script else None
        self.critic_provider = ScriptedProvider(review_script)
        self.runtime = EvaluationRuntime(
            self.repo,
            self.port,
            None if controls.get("meter_missing") else ScriptedMeter(),
            offline=True,
            critic=self.critic,
            critic_meter=ScriptedMeter(),
        )

    def _draw_selection(self, turn: dict[str, Any]) -> tuple[str | None, list[str]]:
        draw_id = None
        if turn.get("kind") == "action":
            if turn.get("action", {}).get("type") != "tarot_reveal":
                raise ValueError("This action needs an implemented v4 evaluation driver")
            draw_id = self.tarot.reveal(turn["action"])
            self.bindings.update(self.tarot.ids)
        script = next(step for step in self.seed["_scripted"] if step["turn"] == turn["_index"])
        draw_id = draw_id or self.tarot.requested(script)
        cases = [self.tarot.cards.get(self.owner, draw_id)["case_id"]] if draw_id else self.seeder.case_ids
        return draw_id, cases

    def _request(self, turn: dict[str, Any]) -> dict[str, Any]:
        if self.repo is None:
            raise RuntimeError("Call reset before send")
        if turn.get("action", {}).get("type") == "ingest_batch" or turn.get("channel") == "feishu":
            self.feishu = FeishuBatchDriver(self)
            return self.feishu.prepare(None if turn.get("action", {}).get("type") == "ingest_batch" else turn)
        index = turn["_index"]
        operation = f"v4-eval:{self.seed['_scenario_id']}:{index}"
        draw_id, cases = self._draw_selection(turn)
        channel, external = turn.get("channel", "web"), None
        if channel == "feishu":
            external = "synthetic-eval-feishu"
            self.repo.bind_channel(self.owner, channel, external)
        if draw_id:
            from mingjing_core.application.tarot_reveal_ingress import TarotRevealIngress

            run = TarotRevealIngress(self.service).submit(
                owner=self.owner,
                thread_id=self.thread["id"],
                message=turn["user"],
                request_id=operation,
                draw_id=draw_id,
                case_ids=cases,
                conversation_id=self.seed.get("context", {}).get("topic_id", "shared"),
                reading_id=self.tarot.failed_reading,
            )
            current = self.repo.fetch_run(self.owner, run["id"])
            self.bindings[f"turn-{index}"] = current["request"]["source_message_id"]
            self.tarot.resume(run)
            return self.repo.claim_run(self.owner, run["id"], lease_seconds=150)
        source = ThreadService(self.repo).receive(
            self.owner,
            self.thread["id"],
            turn["user"],
            request_id=operation,
            channel=channel,
            external_id=external,
            conversation_id=self.seed.get("context", {}).get("topic_id", "shared"),
            case_ids=cases,
        )
        self.bindings[f"turn-{index}"] = source["id"]
        run = ThreadIngress(self.service).queue(
            owner=self.owner,
            thread_id=self.thread["id"],
            source_ids=[source["id"]],
            request_id=operation,
            conversation_id=self.seed.get("context", {}).get("topic_id", "shared"),
            case_ids=cases,
            draw_id=draw_id,
            reading_id=self.tarot.failed_reading if draw_id else None,
            depth="standard",
        )
        if draw_id:
            self.tarot.resume(run)
        return self.repo.claim_run(self.owner, run["id"], lease_seconds=150)

    def _start_turn(self, turn: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        resumed = None
        if turn.get("action", {}).get("type") == "resume_run":
            if not self.crashed_run or turn["action"]["operation_id"] != self.seed["controls"]["operation_id"]:
                raise ValueError("No exact synthetic crashed operation to resume")
            run, resumed = reclaim_crashed(self.repo, self.owner, self.crashed_run)
        else:
            run = self._request(turn)
            self.run_ids.append(run["id"])
        self.port.start(self.provider, turn["_index"], self.bindings)
        if isinstance(self.port, FaultScriptedPort):
            self.port.failure = self.seed.get("controls", {}).get("provider_failures", {}).get(str(turn["_index"]))
            configure_withdrawal(self, run)
        if self.critic:
            self.critic.start(self.critic_provider, turn["_index"], self.bindings)
        return run, resumed

    def _attempt(self, run: dict[str, Any], events: list[dict]) -> tuple[dict, dict | None, str | None, bool]:
        result: dict[str, Any] = {}
        error, retry, crashed = None, None, False
        try:
            result = self.runtime.execute(self.service, self.owner, run["id"], run["lease_token"], events.append)
            retry = self.tarot.finish(result)
        except SystemExit:
            self.crashed_run, crashed = run["id"], True
        except Exception as exc:
            error = type(exc).__name__
        return result, retry, error, crashed

    def _semantics(
        self,
        steps: list[dict],
        turn: dict,
        *,
        result: dict,
        retry: dict | None,
        resumed: dict | None,
        crashed: bool,
        run_id: str,
    ) -> list[dict]:
        semantic = semantic_observations(steps)
        if self.http_faults is not None:
            semantic.extend(self.http_faults.observations())
        if crashed:
            semantic += crash_observations(steps, run_id)
        if resumed:
            semantic.insert(0, resumed)
        if result and retry:
            semantic.insert(0, retry)
        semantic.extend(withdrawal_observations(self, run_id))
        if result and self.seed.get("controls", {}).get("model_matrix") and not self.protocol:
            self.portability = run_matrix(self.seed, turn, self.dsn)
            if not self.portability["protocol_errors"]:
                semantic.append(
                    {
                        "name": "portability.protocol_passed",
                        "source_store": "four isolated PG runs + MockTransport wire proofs",
                        "proofs": self.portability["proofs"],
                        "rule": "all committed; encoded tool results roundtripped",
                    }
                )
        return semantic

    def send(self, turn: dict[str, Any]) -> TurnResult:
        from .v4_judge_evidence import judge_evidence

        if turn.get("action", {}).get("type") == "sse_reconnect":
            return reconnect(self, turn)
        if turn.get("action", {}).get("type") in {"fact_revoke", "source_delete"}:
            return NativePrivacyDriver(self).execute(turn)
        started, before = (
            time.perf_counter(),
            self.port.calls + (self.critic.calls if self.critic else 0),
        )
        request_offset = len(self.port.requests)
        if turn.get("action", {}).get("type") == "cancel_run":
            return self._cancel(turn, started)
        run, resumed = self._start_turn(turn)
        events: list[dict[str, Any]] = []
        result, retry, error, crashed = self._attempt(run, events)
        delivered = self.feishu.finish(run["id"]) if result and self.feishu else []
        current = self.repo.fetch_run(self.owner, run["id"])
        steps = tool_steps(self.repo, self.owner, run["id"])
        semantic = self._semantics(
            steps,
            turn,
            result=result,
            retry=retry,
            resumed=resumed,
            crashed=crashed,
            run_id=run["id"],
        )
        semantic.extend(delivered)
        semantic.extend(structural_observations(current))
        if self.seed.get("_scenario_id") == "X01":
            semantic.extend(review_observations(self.repo, self.owner, current))
        names = [event["type"] for event in events]
        if semantic:
            names = [name for name in names if name != "final"] + [item["name"] for item in semantic]
        if current["status"] == "succeeded":
            names += ["run.completed"]
        self.semantic = semantic
        self.semantic_history += semantic
        self.tool_visibility_history.append(
            {
                "turn": turn["_index"],
                "run_id": run["id"],
                "visible_tools_per_request": [
                    request.get("tool_names", []) for request in self.port.requests[request_offset:]
                ],
                "actual_tool_names": [step["name"] for step in steps],
            }
        )
        return TurnResult(
            text=result.get("text", ""),
            tools_called=[step["name"] for step in steps],
            receipts=result.get("receipts", [])
            if current["status"] == "succeeded"
            else [step["output"]["receipt"] for step in steps if (step["output"] or {}).get("receipt")],
            events=names,
            model_calls=self.port.calls
            + (self.critic.calls if self.critic else 0)
            - before
            + self.portability.get("model_calls", 0),
            elapsed_seconds=round(time.perf_counter() - started, 4),
            error=error,
            metadata={
                "runtime": "v4",
                "run_id": run["id"],
                "run_status": current["status"],
                "offline": True,
                "physical_model_requests": 0,
                "evaluator_observations": semantic,
                "error_category": "business" if error else None,
                "tool_effects": tool_effects(self.repo, self.owner, run["id"]),
                "prior_turns": sorted(
                    previous_turns(self.repo, self.owner, self.run_ids[:-1]) + self.judge_action_history,
                    key=lambda row: row["turn"],
                ),
                "judge_evidence": judge_evidence(self, current),
                "visible_tools_per_request": [
                    request.get("tool_names", []) for request in self.port.requests[request_offset:]
                ],
                "actual_tool_names": [step["name"] for step in steps],
            },
        )

    def _cancel(self, turn: dict[str, Any], started: float) -> TurnResult:
        self.cancellation = cancel_stream(
            self.repo,
            self.owner,
            partial=self.seed["controls"]["partial_text"],
            after_ms=turn["action"]["after_ms"],
        )
        self.run_ids.append(self.cancellation["run_id"])
        return TurnResult(
            events=["run.cancel_requested", "stream.stopped"],
            model_calls=self.cancellation["scripted_http_requests"],
            elapsed_seconds=time.perf_counter() - started,
            metadata={
                "offline": True,
                "physical_model_requests": 0,
                "evaluator_observations": [self.cancellation],
            },
        )

    def inspect_db(self) -> dict[str, Any]:
        if self.repo is None:
            raise RuntimeError("Call reset before inspect_db")
        kinds = {
            kind: self.repo.list(self.owner, kind, include_deleted=True)
            for kind in sorted(ENTITY_KINDS)
            if kind not in {"model_call", "runtime_step"}
        }
        zone = self.repo.assert_scope(self.owner)["settings"].get("timezone", "Asia/Shanghai")
        rows = [
            {
                "id": row["id"],
                "kind": kind,
                "status": row["status"],
                "data": local_entity(row, zone),
            }
            for kind, values in kinds.items()
            for row in values
            if kind != "fact" or row["id"] not in self.seeder.profile_fact_ids
        ]
        steps = tool_steps(self.repo, self.owner, self.run_ids[-1]) if self.run_ids else []
        run = self.repo.fetch_run(self.owner, self.run_ids[-1]) if self.run_ids else {}
        rows += decision_rows(steps)
        rows += self.tarot.rows()
        rows += delivery_rows(self.repo, self.owner)
        rows += native_run_rows(self.repo, self.owner)
        if self.seed.get("_scenario_id") in {"F01", "F02", "F03"}:
            rows = privacy_entities(
                self.repo, self.owner, self.seeder.privacy_layers, rows, self.seeder.privacy_aliases
            )
        return {
            "entities": rows,
            "settings": self.repo.assert_scope(self.owner)["settings"],
            "run_meta": {
                **native_run_meta(self.repo, self.owner, run),
                "privacy_initial_layers": self.privacy_initial,
                "repeated_call_count": repeat_count(steps),
                "usage": run.get("usage", {}),
                **regeneration_state(run),
                **({"ingress": self.feishu.proof} if self.feishu else {}),
                **self.cancellation,
            },
            "evaluator_observations": semantic_observations(steps),
            "portability": self.portability,
            "observed_tools": steps,
            "context": context_observations(self.repo, self.owner, run),
            "run_result": run.get("result") or {},
            **kinds,
            "chart": chart_observations(kinds.get("artifact", []), self.owner, run),
            **({"stream": self.stream} if self.stream else {}),
            **fault_evidence(self.port),
        }

    def close(self) -> None:
        if self.repo is None:
            return
        repo, self.repo = self.repo, None
        try:
            if not re.fullmatch(r"eval_v4_[a-f0-9]{32}", self.schema):
                raise ValueError("Refusing cleanup outside this evaluation schema")
            with repo.transaction() as connection:
                connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        finally:
            repo.close()
            self.run_ids, self.bindings = [], {}

    def case_evidence(self) -> dict[str, Any]:
        if self.repo is None or not self.run_ids:
            return {"observed_runs": 0, "external_provider_requests": 0}
        steps = tool_steps(self.repo, self.owner, self.run_ids[-1])
        return {
            "run_ids": list(self.run_ids),
            "external_provider_requests": 0,
            "u4_scope": "actual shared U4 parser; scripted model output, no live-language quality claim",
            "tool_steps": [{key: step[key] for key in ("run_id", "epoch", "seq", "name", "status")} for step in steps],
            "semantic_observations": self.semantic_history,
            "tool_visibility_by_turn": self.tool_visibility_history,
            "decision_rows": [
                {key: row[key] for key in ("id", "source_store", "source_seq")} for row in decision_rows(steps)
            ],
            "cancellation": self.cancellation,
            "portability": self.portability,
            "ingress": self.feishu.proof if self.feishu else {},
            **harness_evidence(self),
            **fault_evidence(self.port),
            **({"stream": self.stream} if self.stream else {}),
        }

"""Live Agent candidate on synthetic loopback PG; tests replace only provider transport."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from mingjing_core.application.production_agent import configured_agent
from mingjing_core.models.port import ModelPort
from mingjing_core.models.registry import ModelHandle, RegistryPort
from tools.eval.model_selection import ProofSelectedRegistry

from .base import TurnResult
from .v4_live_ports import LiveTrackingPort
from .v4_target import V4Target


class V4LiveTarget(V4Target):
    def __init__(
        self,
        *,
        model: str,
        dsn: str | None = None,
        environment: Mapping[str, str] | None = None,
        adapter_factory: Callable[[ModelHandle], ModelPort] | None = None,
    ) -> None:
        super().__init__(dsn=dsn, candidate=model)
        self.model = model
        self.environment = os.environ if environment is None else environment
        self.adapter_factory = adapter_factory

    def reset(self, seed: dict[str, Any]) -> None:
        forbidden = {"model_matrix", "provider_failures", "crash_after", "critic_scripted", "meter_missing"}
        if forbidden.intersection(seed.get("controls", {})):
            raise ValueError("Live target cannot execute scripted provider fault controls")
        super().reset(seed)

    def _ports(self) -> None:
        # The disposable evaluation repository deliberately reserves all three lanes.
        self.repo.max_running = 3
        runtime = configured_agent(self.repo, environment=self.environment, registry_factory=ProofSelectedRegistry)
        if runtime is None or not isinstance(runtime.port, RegistryPort):
            raise ValueError("Live v4 requires explicitly enabled production Agent assembly")
        handles = runtime.port.registry.resolve("primary")
        if any(handle.model != self.model for handle in handles):
            raise ValueError("Requested candidate differs from the locked production model")
        if self.adapter_factory is not None:
            runtime.port.factory = self.adapter_factory
        self.port = LiveTrackingPort(runtime.port)
        runtime.port = self.port
        self.critic, self.runtime = None, runtime

    def _draw_selection(self, turn: dict[str, Any]) -> tuple[str | None, list[str]]:
        draw_id = None
        if turn.get("kind") == "action":
            if turn.get("action", {}).get("type") != "tarot_reveal":
                raise ValueError("Live action needs an implemented production driver")
            draw_id = self.tarot.reveal(turn["action"])
            self.bindings.update(self.tarot.ids)
        elif turn.get("channel") == "tarot":
            draws = self.tarot.cards.list_draws(self.owner)
            if len(draws) != 1 or draws[0]["status"] != "ready":
                raise ValueError("Live tarot input must identify one already revealed draw")
            draw_id = draws[0]["id"]
        cases = [self.tarot.cards.get(self.owner, draw_id)["case_id"]] if draw_id else self.seeder.case_ids
        return draw_id, cases

    def _start_turn(self, turn: dict[str, Any]) -> tuple[dict[str, Any], None]:
        if turn.get("action", {}).get("type") in {"cancel_run", "resume_run"}:
            raise ValueError("Live target cannot replace process faults with scripted recovery")
        self.port.begin_turn()
        run = self._request(turn)
        self.run_ids.append(run["id"])
        return run, None

    def send(self, turn: dict[str, Any]) -> TurnResult:
        if turn.get("action", {}).get("type") == "cancel_run":
            raise ValueError("Live cancellation requires a separate actual-provider driver")
        before = self.port.external_calls
        result = super().send(turn)
        result.metadata.update(
            offline=False,
            physical_model_requests=result.model_calls,
            external_provider_requests=self.port.external_calls - before,
            input_meter="pinned local official K3 encoder",
            u4_parser="actual shared ModuleTimeRangeParser",
        )
        run = self.repo.fetch_run(self.owner, self.run_ids[-1])
        result.usage = run.get("usage", {}).get("reported_tokens", {})
        return result

    def case_evidence(self) -> dict[str, Any]:
        evidence = super().case_evidence()
        evidence.update(
            physical_model_requests=self.port.calls if self.repo is not None else 0,
            external_provider_requests=self.port.external_calls if self.repo is not None else 0,
            u4_scope="actual shared U4 parser with production AgentRuntime",
            input_meter="pinned local official K3 encoder",
            internal_model_critic=False,
        )
        return evidence

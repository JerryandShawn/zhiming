"""Epoch-pinned program time and body-free audit records for the isolated P6 draft."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mingjing_core.application.agent_runtime_state import RuntimeState
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint
from mingjing_core.timekit.clock import FrozenClock, get_clock


class P6Records:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo
        self.state = RuntimeState(repo)

    def clock(self, run: dict[str, Any]) -> FrozenClock:
        ident = f"{run['id']}:e{run['retry_epoch']}:p6_clock"
        with self.repo.transaction(run["owner"]):
            current = self.state.authority(run["owner"], run["id"], run["lease_token"])
            try:
                saved = self.repo.get(run["owner"], "runtime_step", ident)
            except ScopeError:
                saved = None
            if saved:
                value = saved.get("output")
                if (
                    saved.get("run_id") != run["id"]
                    or saved.get("epoch") != run["retry_epoch"]
                    or fingerprint(value) != saved.get("output_sha256")
                ):
                    raise EvidenceError("P6固定时刻记录已失效")
                return FrozenClock(datetime.fromisoformat(value["program_at"]))
            clock = FrozenClock(get_clock().now())
            value = {"program_at": clock.now().isoformat()}
            self._put(current, ident, value)
            return clock

    def record(self, run: dict[str, Any], phase: str, value: dict[str, Any]) -> None:
        if phase not in {"draft", "final"}:
            raise EvidenceError("P6阶段标识无效")
        ident = f"{run['id']}:e{run['retry_epoch']}:p6_{phase}:" + value["before_sha256"][:24]
        with self.repo.transaction(run["owner"]):
            current = self.state.authority(run["owner"], run["id"], run["lease_token"])
            self._put(current, ident, value)
            previous = current["usage"].get("agent_runtime", {}).get("p6_validation", {})
            mode = "evidence_only" if "evidence_only" in {previous.get("mode"), value["mode"]} else value["mode"]
            self.state.metadata(
                current, p6_validation={"draft": True, "phase": phase, "record_id": ident, "mode": mode}
            )

    def _put(self, run: dict[str, Any], ident: str, value: dict[str, Any]) -> None:
        self.repo.put(
            run["owner"],
            "runtime_step",
            ident,
            {
                "schema": "p6-wire-draft-v1",
                "stage": "p6_wire",
                "run_id": run["id"],
                "epoch": run["retry_epoch"],
                "output": value,
                "output_sha256": fingerprint(value),
            },
            subject=run["subject"],
            expected_revision=0,
            operation_id=ident,
        )

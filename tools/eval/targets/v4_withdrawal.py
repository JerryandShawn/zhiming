"""Withdraw a genuinely injected source at a scripted provider boundary."""

from __future__ import annotations

from typing import Any

from mingjing_core.application.agent_snapshots import STAGE

from .v4_faults import FaultScriptedPort


class WithdrawalFault:
    def __init__(self, target: Any, run: dict[str, Any], ident: str) -> None:
        self.target, self.run, self.ident = target, run, ident
        self.applied = False

    def apply(self) -> None:
        target, run = self.target, self.run
        fact = target.repo.get(target.owner, "fact", self.ident)
        saved = target.repo.get(target.owner, "runtime_step", f"{run['id']}:e{run['retry_epoch']}:{STAGE}")
        if (
            saved.get("run_id") != run["id"]
            or saved.get("epoch") != run["retry_epoch"]
            or self.ident not in saved.get("fact_ids", [])
            or fact["subject_id"] != run["subject"]
        ):
            raise ValueError("Withdrawal fault requires an actually injected fact of this run")
        target.service.memory.retire_fact(
            target.owner, self.ident, expected_revision=fact["revision"], scope="source"
        )
        self.applied = True


def configure_withdrawal(target: Any, run: dict[str, Any]) -> None:
    marker = target.seed.get("controls", {}).get("revoke_after_context")
    if marker is None:
        return
    if not isinstance(target.port, FaultScriptedPort) or marker not in target.bindings:
        raise ValueError("Withdrawal fault needs an explicit existing synthetic fact")
    if target.port.before_first_model is not None:
        return
    fault = WithdrawalFault(target, run, target.bindings[marker])
    target.port.withdrawal_fault = fault
    target.port.before_first_model = fault.apply


def regeneration_state(run: dict[str, Any]) -> dict[str, int]:
    value = run.get("usage", {}).get("agent_runtime", {}).get("regenerations")
    return {"regenerations": value} if type(value) is int else {}


def withdrawal_observations(target: Any, run_id: str) -> list[dict[str, Any]]:
    fault = getattr(target.port, "withdrawal_fault", None)
    if not isinstance(fault, WithdrawalFault) or not fault.applied:
        return []
    run = target.repo.fetch_run(target.owner, run_id)
    if (
        run["status"] != "succeeded"
        or run["retry_epoch"] != fault.run["retry_epoch"] + 1
        or regeneration_state(run) != {"regenerations": 1}
        or not target.repo.is_revoked(target.owner, "fact", fault.ident)
    ):
        return []
    return [
        {
            "name": name,
            "source_store": "core_revocations + core_runs.retry_epoch/usage",
            "run_id": run_id,
            "epoch": run["retry_epoch"],
            "fact_id": fault.ident,
            "rule": "real withdrawal after persisted context, then exactly one clean completed epoch",
        }
        for name in ("context.invalidated", "run.regenerated")
    ]

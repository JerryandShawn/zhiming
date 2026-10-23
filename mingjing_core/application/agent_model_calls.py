"""Persist the exact bounded request and meter before each physical model call."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from mingjing_core.agent.context_budget import assert_live_allowed
from mingjing_core.agent.context_k3 import K3EstimatedMeter
from mingjing_core.agent.context_tokens import TokenMeter
from mingjing_core.agent.context_types import (
    BudgetResult,
    ContextBuild,
    ContextEpoch,
    InputMeterUnverified,
    MeterResult,
)
from mingjing_core.agent.journal import Journal, JournalStep
from mingjing_core.application.agent_snapshots import _decode
from mingjing_core.application.agent_thread_scope import thread_id
from mingjing_core.application.context_epochs import ContextEpochService
from mingjing_core.application.context_usage import ContextUsageService
from mingjing_core.domain.contracts import EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


@dataclass(frozen=True)
class PreparedModelCall:
    budget: BudgetResult = field(repr=False)
    choice: str
    versions: dict[str, int]
    plan: ContextEpoch
    role: str
    name: str


class RequestLedger:
    def __init__(self, repo: PostgresRepository, meter: TokenMeter, *, offline: bool) -> None:
        self.repo, self.base_meter, self.offline = repo, meter, offline
        self.epochs, self.usage = ContextEpochService(repo), ContextUsageService(repo)

    def meter(self, run: dict[str, Any]) -> TokenMeter:
        base = self.base_meter
        if not isinstance(base, K3EstimatedMeter):
            return base
        identity = replace(
            MeterResult(0, 0),
            token_meter_version=base.version,
            provider=base.provider,
            model=base.model,
            tokenizer_version=base.tokenizer_version,
            tokenizer_sha256=base.tokenizer_sha256,
            encoder_version=base.encoder_version,
            encoder_sha256=base.encoder_sha256,
            estimate_multiplier=base.estimate_multiplier,
        )
        factor = self.usage.factor(run["owner"], run["subject"], thread_id(run), identity)
        return K3EstimatedMeter(base.counter, factor=factor, model=base.model)

    @staticmethod
    def _id(run_id: str, epoch: int, seq: int) -> str:
        return f"{run_id}:e{epoch}:agent_model_request:{seq}"

    def _load(self, owner: str, run_id: str, epoch: int, seq: int) -> PreparedModelCall | None:
        try:
            row = self.repo.get(owner, "runtime_step", self._id(run_id, epoch, seq), include_deleted=True)
        except ScopeError:
            return None
        output = row.get("output")
        if (
            row["status"] != "active"
            or row.get("schema") != "agent-model-request-v1"
            or (row.get("run_id"), row.get("epoch"), row.get("seq")) != (run_id, epoch, seq)
            or fingerprint(output) != row.get("output_sha256")
        ):
            raise EvidenceError("模型请求快照失效，不能复用")
        try:
            budget = _decode(BudgetResult, output["budget"])
            plan = _decode(ContextEpoch, output["plan"])
            result = PreparedModelCall(
                budget, output["choice"], output["versions"], plan, output["role"], output["name"]
            )
        except (KeyError, TypeError, ValueError):
            raise EvidenceError("模型请求快照格式不符") from None
        self._admit(budget)
        return result

    def _admit(self, budget: BudgetResult) -> None:
        if self.offline:
            if budget.meter.provider != "scripted" or budget.meter.live_admissible:
                raise InputMeterUnverified()
        else:
            assert_live_allowed(budget)

    def restore_next(self, journal: Journal, run: dict[str, Any], *, role: str, name: str) -> PreparedModelCall | None:
        result = self._load(run["owner"], run["id"], run["retry_epoch"], journal.next_position(run))
        if result is not None and (result.role != role or result.name != name):
            raise EvidenceError("模型请求恢复角色或步骤名称不符")
        return result

    def reserve(
        self,
        step: JournalStep,
        frozen: ContextBuild,
        budget: BudgetResult,
        choice: str,
        versions: dict[str, int],
        *,
        role: str = "primary",
    ) -> PreparedModelCall:
        self._admit(budget)
        with self.repo.transaction(step.owner):
            run = self.repo.fetch_run(step.owner, step.run_id)
            saved = self._load(step.owner, step.run_id, step.epoch, step.seq)
            plan = (
                saved.plan
                if saved
                else self.epochs.preview(
                    step.owner,
                    step.subject,
                    thread_id(run),
                    budget,
                    versions,
                    frozen.snapshot_revision,
                    role=role,
                    case_ids=tuple(run["request"].get("case_ids", [])),
                )
            )
            context = replace(frozen, budget=budget, injected_versions=versions, cache_epoch=plan)
            self.epochs.mark_sent(step, context, tool_choice=choice, role=role)
            prepared = PreparedModelCall(budget, choice, dict(versions), plan, role, step.name)
            if saved is not None:
                if fingerprint(asdict(prepared)) != fingerprint(asdict(saved)):
                    raise EvidenceError("原模型请求快照不能覆盖")
                return saved
            self._save(step, prepared)
            return prepared

    def _save(self, step: JournalStep, call: PreparedModelCall) -> None:
        value = json.loads(json.dumps(asdict(call), ensure_ascii=False, allow_nan=False))
        if len(json.dumps(value, ensure_ascii=False).encode()) > 4_000_000:
            raise EvidenceError("模型请求快照超过私密存储上限")
        ident = self._id(step.run_id, step.epoch, step.seq)
        self.repo.put(
            step.owner,
            "runtime_step",
            ident,
            {
                "schema": "agent-model-request-v1",
                "stage": "agent_model_request",
                "run_id": step.run_id,
                "epoch": step.epoch,
                "seq": step.seq,
                "input_fp": step.input_fp,
                "output": value,
                "output_sha256": fingerprint(value),
                "source_ids": [key[8:] for key in call.versions if key.startswith("message:")],
                "fact_ids": [key[5:] for key in call.versions if key.startswith("fact:")],
            },
            subject=step.subject,
            expected_revision=0,
            operation_id=step.operation_id + ":model_request",
        )

    def completed(self, step: JournalStep) -> dict[str, Any]:
        from .agent_model_attempts import confirmed, verify_completed

        with confirmed(only_core=True):
            verify_completed(self.repo, step, offline=self.offline)
            call = self._load(step.owner, step.run_id, step.epoch, step.seq)
            if call is None:
                raise EvidenceError("完成模型步骤缺少原始计量")
            return self.usage.record(step, call.budget.meter)

    @contextmanager
    def physical(self, step: JournalStep) -> Iterator[None]:
        from .agent_model_attempts import physical_step

        with physical_step(self.repo, step, offline=self.offline):
            yield

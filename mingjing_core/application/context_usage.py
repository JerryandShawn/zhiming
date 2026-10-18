"""Idempotent metadata-only D2 streaks, driven by durable completed model steps."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.context_types import MeterResult
from mingjing_core.agent.journal import JournalStep
from mingjing_core.domain.contracts import EvidenceError, LeaseConflict, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


def _number(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise EvidenceError("模型用量必须是非负整数或未知")
    return value


def _advance(state: dict[str, Any], actual: int | None, upper: int | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in (("actual", actual), ("measured_upper", upper)):
        previous = state.get(name + "_streak", 0)
        if type(previous) is not int or previous < 0:
            raise EvidenceError("线程用量计数损坏，需检查")
        streak = previous + 1 if value is not None and value > 60_000 else 0
        result[name + "_streak"] = streak
        result[name + "_alert"] = streak == 3
        result[name + "_alert_pending"] = state.get(name + "_alert_pending", False) is True or streak == 3
    return result


class ContextUsageService:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo

    def record(self, step: JournalStep, preflight: MeterResult) -> dict[str, Any]:
        if step.kind != "model" or not step.completed:
            raise EvidenceError("上下文用量只能确认已持久完成的模型步骤")
        return self._record(step, preflight)

    def _record(self, step: JournalStep, preflight: MeterResult) -> dict[str, Any]:
        with self.repo.transaction(step.owner) as connection:
            run = self.repo._leased(connection, step.owner, step.run_id, step.lease_token)
            if run["runtime"] != "v4" or run["retry_epoch"] != step.epoch:
                raise LeaseConflict("上下文用量批次不符")
            if run["subject"] != step.subject:
                raise ScopeError("上下文用量人物不符")
            self.repo.assert_scope(step.owner, step.subject)
            stored = connection.execute(
                sql.SQL(
                    "SELECT kind,status,input_fp,usage FROM {} WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s"
                ).format(self.repo.table("core_run_steps")),
                (step.owner, step.run_id, step.epoch, step.seq),
            ).fetchone()
            if (
                not stored
                or stored["kind"] != "model"
                or stored["status"] != "completed"
                or stored["input_fp"] != step.input_fp
            ):
                raise EvidenceError("上下文用量缺少完成步骤")
            digest = fingerprint(asdict(preflight))
            recorded = run["usage"].get("context_steps", {})
            if step.operation_id in recorded:
                old = recorded[step.operation_id]
                if old.get("meter_fp") != digest:
                    raise EvidenceError("完成步骤的计量不能被覆盖")
                return old["receipt"]
            actual = _number(stored["usage"].get("input_tokens", stored["usage"].get("prompt_tokens")))
            upper = _number(preflight.input_token_upper_bound)
            thread_id = run["thread_id"] or "life:" + step.subject
            state = self._thread(step.owner, step.subject, thread_id)
            counters = _advance(state.get("context_guard", {}), actual, upper)
            receipt = dict(
                counters,
                actual_input_tokens=actual,
                estimated_input_tokens=preflight.estimated_input_tokens,
                input_token_upper_bound=upper,
                token_meter_version=preflight.token_meter_version,
                operation_id=step.operation_id,
            )
            self._save_thread(step, thread_id, state, counters)
            recorded = dict(recorded, **{step.operation_id: {"meter_fp": digest, "receipt": receipt}})
            usage = dict(run["usage"], context_guard=receipt, context_steps=recorded)
            connection.execute(
                sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
                (Jsonb(usage), step.owner, step.run_id),
            )
            return receipt

    def _save_thread(self, step: JournalStep, thread_id: str, state: dict[str, Any], counters: dict[str, Any]) -> None:
        self.repo.put(
            step.owner,
            "thread",
            thread_id,
            dict(state, context_guard=counters),
            subject=step.subject,
            expected_revision=state.get("revision", 0),
            operation_id=step.operation_id + ":context_guard",
        )

    def _thread(self, owner: str, subject: str, thread_id: str) -> dict[str, Any]:
        try:
            state = self.repo.get(owner, "thread", thread_id)
        except ScopeError:
            return {"mode": "life" if thread_id == "life:" + subject else "incognito"}
        if state["subject_id"] != subject:
            raise ScopeError("上下文线程不属于当前人物")
        return state

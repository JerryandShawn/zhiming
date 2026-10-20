"""Lease-fenced cache-epoch reservation immediately before a physical model send."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.context_epochs import epoch_plan
from mingjing_core.agent.context_types import BudgetResult, ContextBuild, ContextEpoch, ContextInputError
from mingjing_core.agent.journal import Journal, JournalStep, input_fingerprint
from mingjing_core.application.agent_commit_versions import assert_no_withdrawal
from mingjing_core.domain.contracts import EvidenceError, RevisionConflict, ScopeError
from mingjing_core.repositories.dependencies import lineage_key
from mingjing_core.repositories.postgres import PostgresRepository, fingerprint


class ContextEpochService:
    def __init__(self, repo: PostgresRepository) -> None:
        self.repo = repo

    def _thread(self, owner: str, subject: str, thread_id: str) -> dict[str, Any]:
        if thread_id.startswith("incognito:"):
            from mingjing_core.application.threads import ThreadService

            return ThreadService(self.repo).get(owner, thread_id, subject=subject)
        if thread_id != "life:" + subject:
            raise ContextInputError("context_thread_unsupported")
        try:
            row = self.repo.get(owner, "thread", thread_id)
        except ScopeError:
            return {"mode": "life"}
        if row["subject_id"] != subject:
            raise ScopeError("上下文缓存线程不属于当前人物")
        return row

    @staticmethod
    def _key(role: str) -> str:
        if role not in {"primary", "critic"}:
            raise ContextInputError("context_cache_role_invalid")
        return "context_cache" if role == "primary" else "context_cache_critic"

    def _invalidated(self, owner: str, previous: dict[str, Any]) -> bool:
        versions = previous.get("source_versions", {})
        if not self.repo.verify_versions(owner, versions):
            return True
        keys = {lineage_key(key) for key in versions}
        for row in self.repo.revocations(owner):
            if row["revision"] <= previous.get("snapshot_revision", 0):
                continue
            if row["kind"] + ":" + row["entity_id"] in keys:
                return True
            if row["kind"] == "source_span" and "message:" + str(row["metadata"].get("message_id")) in keys:
                return True
        return False

    @staticmethod
    def _visibility(case_ids: tuple[str, ...] | list[str]) -> str:
        if len(case_ids) > 8 or any(not isinstance(ident, str) or not ident for ident in case_ids):
            raise ContextInputError("context_case_scope_invalid")
        return fingerprint({"case_ids": sorted(set(case_ids))})

    def _view_invalidated(self, owner: str, previous: dict[str, Any], visibility: str) -> bool:
        # Valid old messages may disappear from a newly restricted case view.
        # Unknown legacy view identity must also start a fresh prefix epoch.
        return bool(previous) and (
            previous.get("visibility_sha256") != visibility or self._invalidated(owner, previous)
        )

    def preview(
        self,
        owner: str,
        subject: str,
        thread_id: str,
        budget: BudgetResult,
        versions: dict[str, int],
        snapshot_revision: int,
        *,
        role: str = "primary",
        case_ids: tuple[str, ...] = (),
    ) -> ContextEpoch:
        with self.repo.transaction(owner):
            previous = self._thread(owner, subject, thread_id).get(self._key(role), {})
            return epoch_plan(
                budget,
                versions,
                snapshot_revision,
                previous,
                invalidated=self._view_invalidated(owner, previous, self._visibility(case_ids)),
            )

    def _validate_send(self, step: JournalStep, context: ContextBuild, budget: BudgetResult, choice: str) -> None:
        identity = {
            "messages": [asdict(row) for row in budget.messages],
            "tools": [asdict(row) for row in budget.tools],
            "tool_choice": choice,
            "source_versions": context.injected_versions,
        }
        if step.kind != "model" or step.input_fp != input_fingerprint("model", step.name, identity):
            raise EvidenceError("发送标记与模型步骤输入不符")
        actual = epoch_plan(budget, context.injected_versions, context.snapshot_revision, {}, invalidated=False)
        if actual.prefix_sha256 != context.cache_epoch.prefix_sha256:
            raise ContextInputError("context_cache_budget_changed")
        if not self.repo.verify_versions(step.owner, context.injected_versions):
            raise RevisionConflict("发送前上下文来源版本已改变")

    def mark_sent(
        self,
        step: JournalStep,
        context: ContextBuild,
        *,
        budget: BudgetResult | None = None,
        tool_choice: str = "auto",
        role: str = "primary",
    ) -> dict[str, Any]:
        if context.cache_epoch is None:
            raise ContextInputError("context_cache_epoch_missing")
        budget = budget or context.budget
        self._key(role)
        if step.name not in ({"", "revision"} if role == "primary" else {"critic"}):
            raise EvidenceError("模型步骤与受信角色不符")
        with self.repo.transaction(step.owner) as connection:
            current = Journal(self.repo, step.owner)._leased(
                connection,
                {
                    "id": step.run_id,
                    "owner": step.owner,
                    "subject": step.subject,
                    "retry_epoch": step.epoch,
                    "lease_token": step.lease_token,
                },
            )
            thread_id = current["thread_id"] or "life:" + step.subject
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("context-epoch:" + step.owner + ":" + thread_id,),
            )
            self._validate_send(step, context, budget, tool_choice)
            assert_no_withdrawal(self.repo, current, context.injected_versions, context.snapshot_revision)
            return self._mark(connection, step, context, current, thread_id, budget, role)

    def _mark(
        self,
        connection: Any,
        step: JournalStep,
        context: ContextBuild,
        run: dict[str, Any],
        thread_id: str,
        budget: BudgetResult,
        role: str,
    ) -> dict[str, Any]:
        stored = connection.execute(
            sql.SQL(
                "SELECT kind,status,input_fp,error_code FROM {} "
                "WHERE owner=%s AND run_id=%s AND epoch=%s AND seq=%s FOR UPDATE"
            ).format(self.repo.table("core_run_steps")),
            (step.owner, step.run_id, step.epoch, step.seq),
        ).fetchone()
        if (
            not stored
            or stored["kind"] != "model"
            or stored["input_fp"] != step.input_fp
            or stored["error_code"]
            or stored["status"] not in {"started", "completed"}
        ):
            raise EvidenceError("发送标记缺少有效模型步骤")
        marks = run["usage"].get("context_sends", {})
        value = asdict(context.cache_epoch)
        digest = fingerprint({"epoch": value, "input_fp": step.input_fp, "role": role})
        if step.operation_id in marks:
            if marks[step.operation_id]["fingerprint"] != digest:
                raise EvidenceError("已有发送标记不能改写上下文")
            return marks[step.operation_id]["receipt"]
        state = self._thread(step.owner, step.subject, thread_id)
        previous = state.get(self._key(role), {})
        if previous.get("generation", 0) != context.cache_epoch.base_generation:
            raise RevisionConflict("上下文缓存代次已改变，请重建发送上下文")
        fresh = epoch_plan(
            budget,
            context.injected_versions,
            context.snapshot_revision,
            previous,
            invalidated=self._view_invalidated(
                step.owner, previous, self._visibility(run["request"].get("case_ids", []))
            ),
        )
        if fresh != context.cache_epoch:
            raise RevisionConflict("发送前上下文压缩周期已改变，请重建")
        receipt = self._save(
            step, context.cache_epoch, thread_id, state, role, self._visibility(run["request"].get("case_ids", []))
        )
        marks = dict(marks, **{step.operation_id: {"fingerprint": digest, "receipt": receipt}})
        usage = dict(run["usage"], context_sends=marks)
        connection.execute(
            sql.SQL("UPDATE {} SET usage=%s WHERE owner=%s AND id=%s").format(self.repo.table("core_runs")),
            (Jsonb(usage), step.owner, step.run_id),
        )
        return receipt

    def _save(
        self,
        step: JournalStep,
        plan: ContextEpoch,
        thread_id: str,
        state: dict[str, Any],
        role: str,
        visibility: str,
    ) -> dict[str, Any]:
        cache = asdict(plan)
        cache.pop("base_generation")
        cache["generation"] = plan.base_generation + 1
        cache["visibility_sha256"] = visibility
        self.repo.put(
            step.owner,
            "thread",
            thread_id,
            dict(state, **{self._key(role): cache}),
            subject=step.subject,
            expected_revision=state.get("revision", 0),
            operation_id=step.operation_id + ":context_sent",
        )
        return {
            "compression_epoch": plan.epoch,
            "generation": cache["generation"],
            "prefix_sha256": plan.prefix_sha256,
            "l5_messages": len(plan.l5_hashes),
            "reset_reason": plan.reset_reason,
            "operation_id": step.operation_id,
            "send_reserved": True,
            "role": role,
        }

"""Explicit lifecycle foundation; attaching never enables execution or quota resume."""

from __future__ import annotations

import re
import uuid
from contextlib import AbstractContextManager
from typing import Any

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError

from .base import TurnResult
from .local_db import verify_local_postgres
from .v4_core30 import Core30LiveTarget
from .v4_execution_budget import ExecutionBudget, execution_scope
from .v4_lifecycle_state import read_private, restore, save_private


class DurableCore30Target(Core30LiveTarget):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.lifecycle_session: str | None = None
        self._attached = False
        self._budget_scope: ExecutionBudget | None = None
        self._budget_started = self._budget_unknown = self._budget_legacy = False
        self._lifecycle_record: dict[str, Any] | None = None
        self._lifecycle_binding: LifecycleBinding | None = None

    def _ports(self) -> None:
        super()._ports()
        self.runtime.control_factory = self._budget_control

    def _execution_scope(
        self, binding: LifecycleBinding, guard: QuotaGuard, run: dict[str, Any]
    ) -> AbstractContextManager[None]:
        self.lifecycle_session = self.lifecycle_session or "eval-" + uuid.uuid4().hex
        return execution_scope(self, binding, guard, run)

    def _budget_control(self, *args: Any, **kwargs: Any) -> Any:
        if self._budget_scope is None:
            raise LifecycleError("Durable控制器必须在原执行scope内构造")
        return self._budget_scope.factory(*args, **kwargs)

    def checkpoint(
        self,
        control: LifecycleControl,
        binding: LifecycleBinding,
        guard: QuotaGuard,
        *,
        turn: int,
        completed: TurnResult | None = None,
    ) -> str:
        if self._budget_scope is not None or self._budget_unknown:
            raise LifecycleError("执行预算未可信闭合，不能保存新检查点")
        binding.verify(guard)
        if self.model != binding.model or self.repo is None or control.schema in {self.schema, guard.store.schema}:
            raise LifecycleError("评测对象与独立控制身份不符")
        self.lifecycle_session = self.lifecycle_session or "eval-" + uuid.uuid4().hex
        from .v4_completed_turn import freeze_completed

        frozen = freeze_completed(self, turn, completed) if completed is not None else None
        ident, digest = save_private(self, self.lifecycle_session, binding, turn, frozen)
        with self.repo.transaction() as connection:
            location = control.location(connection, self.schema)
        record = control.save(
            self.lifecycle_session,
            binding,
            guard,
            target_schema=self.schema,
            target_location=location,
            state_id=ident,
            state_sha256=digest,
        )
        self._lifecycle_record, self._lifecycle_binding = record, binding
        return self.lifecycle_session

    def detach(self) -> None:
        if self._budget_scope is not None or self._budget_unknown:
            raise LifecycleError("活跃或未知执行段不能detach")
        if self.repo is None or self._lifecycle_record is None or self._lifecycle_binding is None:
            raise LifecycleError("未持久保存的场景不能detach")
        read_private(self.repo, self.owner, self._lifecycle_record, self._lifecycle_binding)
        repo, self.repo = self.repo, None
        repo.close()
        # Retain identifiers for diagnostics only; a fresh attach must re-read PG.
        self._attached = True

    def completed_result(self, control: LifecycleControl, binding: LifecycleBinding, guard: QuotaGuard) -> TurnResult:
        from .v4_completed_turn import verify_completed

        if self.repo is None or self.lifecycle_session is None:
            raise LifecycleError("请先附着原场景")
        record = control.load(self.lifecycle_session, binding, guard)
        state = read_private(self.repo, self.owner, record, binding)
        if state.get("phase") != "primary_complete":
            raise LifecycleError("原运行尚未完成，不能只读评分")
        return verify_completed(self.repo, self.owner, state["completed_turn"])

    def attach(self, control: LifecycleControl, session: str, binding: LifecycleBinding, guard: QuotaGuard) -> None:
        if self.repo is not None or self.model != binding.model:
            raise LifecycleError("attach需要空对象及同一受信模型")
        record = control.load(session, binding, guard)
        schema = record["target_schema"]
        if re.fullmatch(r"eval_v4_[a-f0-9]{32}", schema or "") is None:
            raise LifecycleError("禁止附着到非评测schema")
        verify_local_postgres(self.dsn)
        repo = PostgresRepository(self.dsn, schema=schema, initialize=False, max_size=4)
        try:
            with repo.transaction() as connection:
                if control.location(connection, schema) != record["target_location"]:
                    raise LifecycleError("原场景数据库定位改变")
            state = read_private(repo, self.owner, record, binding)
            self.repo, self.schema = repo, schema
            restore(self, state)
        except BaseException:
            self.repo = None
            repo.close()
            raise
        self.lifecycle_session, self._attached = session, True
        self._lifecycle_record, self._lifecycle_binding = record, binding

    def reset(self, seed: dict[str, Any]) -> None:
        if self._budget_scope is not None:
            raise LifecycleError("活跃执行scope不能reset")
        super().reset(seed)
        self.lifecycle_session, self._attached = None, False
        self._budget_started = self._budget_unknown = self._budget_legacy = False
        self._lifecycle_record = self._lifecycle_binding = None

    def send(self, turn: dict[str, Any]) -> TurnResult:
        if self._attached:
            raise LifecycleError("生命周期attach仅恢复观察，尚未开放同run执行")
        return super().send(turn)

    def resume_pending(self, witness, *, control, binding, guard) -> TurnResult:
        from .v4_resume_pending import resume_pending

        return resume_pending(self, witness, control=control, binding=binding, guard=guard)

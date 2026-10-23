"""Explicit lifecycle foundation; attaching never enables execution or quota resume."""

from __future__ import annotations

import re
import uuid
from typing import Any

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.repositories.postgres import PostgresRepository
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError

from .base import TurnResult
from .local_db import verify_local_postgres
from .v4_core30 import Core30LiveTarget
from .v4_lifecycle_state import read_private, restore, save_private


class DurableCore30Target(Core30LiveTarget):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.lifecycle_session: str | None = None
        self._attached = False

    def checkpoint(self, control: LifecycleControl, binding: LifecycleBinding, guard: QuotaGuard, *, turn: int) -> str:
        binding.verify(guard)
        if self.model != binding.model or self.repo is None or control.schema in {self.schema, guard.store.schema}:
            raise LifecycleError("评测对象与独立控制身份不符")
        self.lifecycle_session = self.lifecycle_session or "eval-" + uuid.uuid4().hex
        ident, digest = save_private(self, self.lifecycle_session, binding, turn)
        with self.repo.transaction() as connection:
            location = control.location(connection, self.schema)
        control.save(
            self.lifecycle_session,
            binding,
            guard,
            target_schema=self.schema,
            target_location=location,
            state_id=ident,
            state_sha256=digest,
        )
        return self.lifecycle_session

    def detach(self) -> None:
        if self.repo is None or self.lifecycle_session is None:
            raise LifecycleError("未持久保存的场景不能detach")
        repo, self.repo = self.repo, None
        repo.close()
        # Retain identifiers for diagnostics only; a fresh attach must re-read PG.
        self._attached = True

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

    def reset(self, seed: dict[str, Any]) -> None:
        super().reset(seed)
        self.lifecycle_session, self._attached = None, False

    def send(self, turn: dict[str, Any]) -> TurnResult:
        if self._attached:
            raise LifecycleError("生命周期attach仅恢复观察，尚未开放同run执行")
        return super().send(turn)

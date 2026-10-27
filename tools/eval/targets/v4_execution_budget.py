"""One execution scope owns timing; model-step monitors never close its segment."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from mingjing_core.agent.loop_policy import LoopPolicy, LoopStopped, RunControl
from mingjing_core.models.errors import ModelCancelled, ModelUnavailable
from mingjing_core.models.quota_delegated_session import require_active
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped

from .v4_execution_budget_store import BudgetStore

CONTROL = (KeyboardInterrupt, SystemExit, GeneratorExit)


def _failure(first: BaseException | None, later: BaseException | None) -> BaseException | None:
    if isinstance(first, CONTROL):
        return first
    if isinstance(later, CONTROL):
        return later
    if isinstance(first, (ProviderStopped, ModelCancelled)) or (
        isinstance(first, ModelUnavailable) and first.global_stop
    ):
        return first
    return first if first is not None else later


class ExecutionBudget:
    def __init__(
        self,
        target: Any,
        binding: LifecycleBinding,
        guard: Any,
        run: dict[str, Any],
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        session = require_active()
        if (
            session.guard is not guard
            or session.phase != "core"
            or session.approval.candidate != binding.candidate_commit
            or target.model != binding.model
            or target._budget_scope is not None
            or target._budget_legacy
            or target._budget_unknown
        ):
            raise LifecycleError("执行预算缺少当前受信执行scope")
        binding.verify(guard)
        self.target, self.binding, self.guard, self.run = target, binding, guard, dict(run)
        self.monotonic, self.started = monotonic, monotonic()
        self.store = BudgetStore(target.repo, target.owner, binding, target.lifecycle_session)
        self.control: BudgetRunControl | None = None
        self.consumed_ns = 0
        self.active = True
        self.lock = threading.RLock()

    def elapsed_ns(self) -> int:
        duration = self.monotonic() - self.started
        if not math.isfinite(duration) or duration < 0:
            raise LifecycleError("实际执行计时不明确")
        return int(duration * 10**9)

    def factory(self, repo: Any, run: dict[str, Any], policy: LoopPolicy, **kwargs: Any) -> BudgetRunControl:
        with self.lock:
            if (
                not self.active
                or repo is not self.target.repo
                or any(
                    run.get(key) != self.run.get(key)
                    for key in ("id", "owner", "subject", "retry_epoch", "lease_token")
                )
            ):
                raise LifecycleError("执行控制器离开原scope或批次")
            if self.control is not None:
                raise LifecycleError("同一执行段不能替换控制器")
            self.consumed_ns, has_text = self.store.open(run, policy)
            self.control = BudgetRunControl(repo, run, policy, budget=self, **kwargs)
            self.control.has_text = has_text
            self.check()
            return self.control

    def check(self) -> None:
        with self.lock:
            if not self.active or self.control is None:
                raise LifecycleError("执行预算没有活跃的原控制器")
            consumed = self.consumed_ns + self.elapsed_ns()
            if consumed >= self.control.policy.seconds * 10**9:
                raise LoopStopped("wall_time_limit")
            if (
                self.control.no_text_seconds is not None
                and not self.control.has_text
                and consumed >= self.control.no_text_seconds * 10**9
            ):
                raise LoopStopped("crisis_no_text")

    def before_send(self) -> None:
        self.check()
        self.control.poll()

    def finish(self) -> None:
        # The duration is measured here, never accepted from a manifest or caller.
        with self.lock:
            self.active = False
            if self.control is None:
                raise LifecycleError("未取得受信控制器，不能生成闭合预算")
            self.binding.verify(self.guard)
            self.store.close(self.elapsed_ns(), self.control.has_text)


class BudgetRunControl(RunControl):
    def __init__(self, *args: Any, budget: ExecutionBudget, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.budget = budget

    def poll(self) -> None:
        # The monitor thread holds this exact object; no ContextVar propagation
        # is assumed when enforcing the persisted cumulative allowance.
        self.budget.check()
        super().poll()


@contextmanager
def execution_scope(target: Any, binding: LifecycleBinding, guard: Any, run: dict[str, Any]) -> Iterator[None]:
    budget = ExecutionBudget(target, binding, guard, run)
    target._budget_scope = budget
    target._budget_started = True
    failure = closing = None
    try:
        with target.port.authorize_before_send(budget.before_send):
            yield
    except BaseException as caught:
        failure = caught
    try:
        budget.finish()
    except BaseException as caught:
        target._budget_unknown = True
        closing = caught
    finally:
        target._budget_scope = None
    selected = _failure(failure, closing)
    if selected is not None:
        if closing is not None and selected is not closing:
            selected.add_note("执行预算未能可信闭合，后续执行保持关闭")
        raise selected

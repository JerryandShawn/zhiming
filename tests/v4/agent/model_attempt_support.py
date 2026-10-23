"""Shared native core-evaluation fixture; no provider network access."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import pytest
from models.test_quota_http_pg import rows
from psycopg import sql

from mingjing_core.agent.journal import Journal
from mingjing_core.application import agent_model_attempts as attempts
from mingjing_core.domain.contracts import EvidenceError
from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval import lifecycle_identity
from tools.eval.lifecycle_identity import LifecycleBinding
from tools.eval.quota import ProviderStopped
from tools.eval.targets.v4_core30 import Core30LiveTarget, load_core30

from .test_eval_lifecycle_pg import seed
from .test_eval_v4_live_pg import Harness
from .test_eval_v4_live_pg import live as live_fixture


@dataclass
class Observed:
    live: Harness
    target: Core30LiveTarget
    case: Any
    adapters: list[Any]

    def send(self):
        return self.target.send({**self.case.turns[0].model_dump(mode="json", exclude={"expect"}), "_index": 1})

    def links(self):
        return [
            row
            for row in self.target.repo.list(self.target.owner, "runtime_step", include_deleted=True)
            if row.get("stage") == "agent_model_attempts"
        ]

    @contextmanager
    def scope(self):
        binding = LifecycleBinding.capture(self.live.guard, "a" * 40, self.case, "k3-256k")
        with attempts.core_observation(
            self.target.repo,
            self.target.owner,
            self.live.guard,
            asdict(binding),
            lambda: binding.verify(self.live.guard),
        ):
            yield


@pytest.fixture
def observed(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch, request):
    with contextmanager(live_fixture.__wrapped__)(p2_repo, monkeypatch) as live:
        # Only the clean-checkout boundary is synthetic; source/contract/PG identity are native.
        monkeypatch.setattr(lifecycle_identity, "candidate_provenance", lambda *args: {"worktree_clean": True})
        case = next(case for case in load_core30() if case.id == getattr(request, "param", "T05"))
        live.session = DelegatedSession(live.guard, live.session.approval, phase="core", scenario_ids=[case.id])
        adapters = []

        def factory(handle):
            adapter = live.factory(handle)
            adapters.append(adapter)
            return adapter

        target = Core30LiveTarget(
            model="k3-256k", dsn=live.guard.store.dsn, environment=live.environment, adapter_factory=factory
        )
        live.targets.append(target)
        before = get_clock()
        try:
            set_clock(FrozenClock(datetime.fromisoformat(case.clock)))
            with live.session.activate(), call_scope(live.session.scope(case.id)):
                target.reset(seed(case))
                yield Observed(live, target, case, adapters)
        finally:
            set_clock(before)
            try:
                live.session.close()
            except GuardRejected as error:
                assert error.kind == "in_flight_limit"
                assert any(row["finished_at"] is None for row in rows(live.guard))


def native_step(observed: Observed):
    target = observed.target
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    with target.repo.transaction(target.owner) as connection:
        row = connection.execute(
            sql.SQL("SELECT * FROM {} WHERE run_id=%s AND kind='model' ORDER BY seq LIMIT 1").format(
                target.repo.table("core_run_steps")
            ),
            (run["id"],),
        ).fetchone()
    return Journal(target.repo, target.owner).next_or_replay(
        run, kind="model", name=row["name"], input_fp=row["input_fp"]
    )


def finish_before_publication(observed: Observed, monkeypatch: pytest.MonkeyPatch):
    original = Journal.complete

    def completed(journal, step, output, usage=None):
        result = original(journal, step, output, usage)
        if step.kind == "model":
            raise EvidenceError("SYNTHETIC_JOURNAL_PUBLICATION_FAILURE")
        return result

    monkeypatch.setattr(Journal, "complete", completed)
    with pytest.raises(ProviderStopped):
        observed.send()
    return native_step(observed)

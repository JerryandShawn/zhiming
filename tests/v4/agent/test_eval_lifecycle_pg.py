"""Native memory/tool persistence survives observation-only attach; HTTP remains mocked."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

import httpx
import psycopg
import pytest
from psycopg import sql

from mingjing_core.application.consultation import ConsultationService
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.source_withdrawal import SourceWithdrawalService
from mingjing_core.application.thread_ingress import ThreadIngress
from mingjing_core.application.threads import ThreadService
from mingjing_core.domain.contracts import CoreError
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock, set_clock
from tools.eval import lifecycle_identity
from tools.eval.lifecycle_control import LifecycleControl
from tools.eval.lifecycle_identity import LifecycleBinding, LifecycleError
from tools.eval.quota import ProviderStopped
from tools.eval.targets.v4_core30 import load_core30
from tools.eval.targets.v4_durable import DurableCore30Target
from tools.eval.targets.v4_privacy_seed import V4PrivacySeeder
from tools.eval.targets.v4_scripted import ForbiddenLegacyModel
from tools.eval.targets.v4_tarot import TarotDriver

from .test_eval_v4_live_pg import Harness, wire
from .test_eval_v4_live_pg import live as live_fixture


@pytest.fixture
def live(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch):
    yield from live_fixture.__wrapped__(p2_repo, monkeypatch)


@dataclass
class Saved:
    target: DurableCore30Target
    control: LifecycleControl
    binding: LifecycleBinding
    session: str
    live: Harness

    def new(self) -> DurableCore30Target:
        result = DurableCore30Target(
            model="k3-256k", dsn=self.target.dsn, environment=self.live.environment, adapter_factory=self.live.factory
        )
        self.live.targets.append(result)
        return result


def seed(case: Any) -> dict[str, Any]:
    result = case.seed.model_dump(mode="json")
    result.update(
        _scenario_id=case.id,
        _clock=case.clock,
        _scripted=[step.model_dump(exclude_none=True) for step in case.scripted],
    )
    return result


@pytest.fixture
def saved(live: Harness, monkeypatch: pytest.MonkeyPatch):
    # Only the clean-checkout boundary is simulated for this uncommitted unit
    # fixture. Candidate/source hashes and native central identity stay checked.
    monkeypatch.setattr(lifecycle_identity, "candidate_provenance", lambda *args: {"worktree_clean": True})
    case = next(case for case in load_core30() if case.id == "M01")
    control = LifecycleControl(live.guard.store.dsn, "eval_control_" + uuid.uuid4().hex)
    control.initialize(live.guard)
    binding = LifecycleBinding.capture(live.guard, "a" * 40, case, "k3-256k")
    target = DurableCore30Target(
        model=binding.model, dsn=live.guard.store.dsn, environment=live.environment, adapter_factory=live.factory
    )
    live.targets.append(target)
    previous = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat(case.clock)))

    def respond(request: httpx.Request) -> httpx.Response:
        if len(live.sent) == 1:
            return wire(
                {
                    "type": "tool_use",
                    "id": "lifecycle-memory",
                    "name": "memory_write",
                    "input": {
                        "message_id": target.bindings["turn-1"],
                        "quote": "我下周三有个面试",
                        "summary": "合成面试",
                        "kind": "event",
                        "date_expression": "下周三",
                    },
                }
            )
        return httpx.Response(
            403,
            headers={"Retry-After": "18000"},
            json={"error": {"type": "permission_error", "message": "5-hour usage limit"}},
        )

    live.primary = respond
    try:
        with live.session.activate(), call_scope(live.session.scope("M01")):
            target.reset(seed(case))
            with pytest.raises(ProviderStopped):
                target.send({**case.turns[0].model_dump(mode="json", exclude={"expect"}), "_index": 1})
        session_id = target.checkpoint(control, binding, live.guard, turn=1)
        yield Saved(target, control, binding, session_id, live)
    finally:
        set_clock(previous)
        schema = target.schema
        for item in live.targets:
            if item.repo is not None:
                item.repo.close()
                item.repo = None
        # All names were generated in this test; no arbitrary cleanup target.
        assert schema.startswith("eval_v4_") and control.schema.startswith("eval_control_")
        with psycopg.connect(live.guard.store.dsn, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(control.schema)))


def counts(saved: Saved, target: DurableCore30Target) -> tuple[int, int, int]:
    with target.repo.transaction(target.owner) as connection:
        return tuple(
            connection.execute(sql.SQL("SELECT count(*) AS n FROM {}").format(target.repo.table(name))).fetchone()["n"]
            for name in ("core_runs", "core_mutation_requests", "core_run_steps")
        )


def forbid_attach_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("attach must not create business effects, acquire permits or POST")

    for cls, name in (
        (ThreadService, "receive"),
        (ThreadIngress, "queue"),
        (V4PrivacySeeder, "seed"),
        (TarotDriver, "seed"),
        (PostgresRepository, "claim_run"),
        (PostgresRepository, "ensure_owner"),
        (QuotaGuard, "acquire"),
        (httpx.Client, "send"),
    ):
        monkeypatch.setattr(cls, name, forbidden)


def test_tool_receipt_ids_and_private_state_survive_detach_attach_without_effects(
    saved: Saved, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = saved.target
    originals = (target.schema, target.thread["id"], dict(target.bindings), list(target.run_ids), counts(saved, target))
    facts = target.repo.list(target.owner, "fact")
    created = next(row for row in facts if row.get("summary") == "合成面试")
    with target.repo.transaction(target.owner) as connection:
        steps = connection.execute(
            sql.SQL(
                "SELECT output FROM {} WHERE run_id=%s AND kind='tool' AND name='memory_write' AND status='completed'"
            ).format(target.repo.table("core_run_steps")),
            (target.run_ids[-1],),
        ).fetchall()
    assert len(steps) == 1 and steps[0]["output"]["receipt"]["fact_id"] == created["id"]
    record = saved.control.load(saved.session, saved.binding, saved.live.guard)
    public = json.dumps(record, default=str)
    assert "合成面试" not in public and "我下周三有个面试" not in public and '"seed"' not in public
    sent = len(saved.live.sent)
    target.detach()
    forbid_attach_effects(monkeypatch)
    attached = saved.new()
    attached.attach(saved.control, saved.session, saved.binding, saved.live.guard)
    assert (
        attached.schema,
        attached.thread["id"],
        attached.bindings,
        attached.run_ids,
        counts(saved, attached),
    ) == originals
    assert attached.repo.get(attached.owner, "fact", created["id"])["revision"] == created["revision"]
    assert len(saved.live.sent) == sent == 2 and attached.port.calls == 2
    with pytest.raises(LifecycleError):
        attached.send({"user": "must not execute", "_index": 1})
    attached.close()
    with saved.control.connect() as connection:
        assert connection.execute("SELECT to_regnamespace(%s) AS n", (originals[0],)).fetchone()["n"] is None


@pytest.mark.parametrize("change", ["source", "model", "contract", "central"])
def test_changed_execution_binding_rejected_without_posts(saved: Saved, change: str) -> None:
    values = {
        "source": {"source_sha256": "c" * 64},
        "model": {"model": "k3"},
        "contract": {"contract_sha256": "c" * 64},
        "central": {"central_identity": str(uuid.uuid4())},
    }
    saved.target.detach()
    with pytest.raises(LifecycleError):
        saved.new().attach(saved.control, saved.session, replace(saved.binding, **values[change]), saved.live.guard)
    assert len(saved.live.sent) == 2


@pytest.mark.parametrize("change", ["cancel", "terminal", "source", "revoke", "epoch"])
def test_native_cancellation_terminal_withdrawal_and_identity_changes_rejected(saved: Saved, change: str) -> None:
    target = saved.target
    target.detach()
    repo = PostgresRepository(target.dsn, schema=target.schema, initialize=False, max_size=1)
    try:
        run = repo.fetch_run(target.owner, target.run_ids[-1])
        source = repo.get(target.owner, "message", run["request"]["source_message_id"])
        if change == "cancel":
            DispatcherCancellation(repo).request(target.owner, run["id"])
        elif change == "terminal":
            repo.fail_run(target.owner, run["id"], "SyntheticTerminal", run["lease_token"])
        elif change == "source":
            repo.update(
                target.owner,
                "message",
                source["id"],
                {"content": "changed synthetic source"},
                expected_revision=source["revision"],
            )
        elif change == "revoke":
            state_id = "eval-lifecycle:" + saved.session
            private = repo.get(target.owner, "runtime_step", state_id)
            assert private["state"]["targets"]["seed"]["synthetic"] is True
            service = ConsultationService(repo, model=ForbiddenLegacyModel(), runtime=target.runtime)
            SourceWithdrawalService(service.memory).delete(
                target.owner,
                run["subject"],
                source["id"],
                expected_revision=source["revision"],
                request_id="withdraw-life",
            )
            with repo.transaction(target.owner) as connection:
                erased = connection.execute(
                    sql.SQL("SELECT status,data FROM {} WHERE owner=%s AND kind='runtime_step' AND id=%s").format(
                        repo.table("core_entities")
                    ),
                    (target.owner, state_id),
                ).fetchone()
            assert erased["status"] == "deleted" and erased["data"] == {}
        else:
            with repo.transaction(target.owner) as connection:
                connection.execute(
                    sql.SQL("UPDATE {} SET retry_epoch=retry_epoch+1 WHERE id=%s").format(repo.table("core_runs")),
                    (run["id"],),
                )
    finally:
        repo.close()
    with pytest.raises((LifecycleError, CoreError)):
        saved.new().attach(saved.control, saved.session, saved.binding, saved.live.guard)
    assert len(saved.live.sent) == 2


def test_missing_control_initialization_does_not_create_tables(saved: Saved) -> None:
    control = LifecycleControl(saved.control.dsn, "eval_control_missing_" + uuid.uuid4().hex)
    with pytest.raises(LifecycleError):
        control.load(saved.session, saved.binding, saved.live.guard)
    with control.connect() as connection:
        assert connection.execute("SELECT to_regnamespace(%s) AS n", (control.schema,)).fetchone()["n"] is None

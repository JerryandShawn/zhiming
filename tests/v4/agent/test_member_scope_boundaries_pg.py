"""Short-lived manual scope cannot disappear, expand, or remain in a pooled worker."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from models.test_quota_guard_pg import configure_central
from models.test_quota_http_pg import rows
from psycopg import sql
from psycopg.types.json import Jsonb

from mingjing_core.agent.loop_codec import ObservedPort
from mingjing_core.agent.loop_policy import LoopPolicy, RunControl
from mingjing_core.application.agent_runtime import AgentRuntime
from mingjing_core.application.dispatcher import AgentDispatcher
from mingjing_core.application.dispatcher_cancellation import DispatcherCancellation
from mingjing_core.application.member_run_scope import member_run_scope
from mingjing_core.domain.contracts import CoreError, EvidenceError
from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import CallScope, call_scope, current_scope
from mingjing_core.repositories.postgres import PostgresRepository

from .member_wire_support import member_port, response
from .test_dispatcher_pg import queued
from .test_loop_cycle_support import SyntheticMeter


@pytest.fixture(name="wire_guard")
def guard_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> QuotaGuard:
    return QuotaGuard(**configure_central(p2_repo, monkeypatch))


def manual_scope(guard: QuotaGuard) -> CallScope:
    guard.begin_batch(
        batch_id="offline-manual-batch",
        scenario_ids=["T01"],
        authorization_id="offline-terminal",
        expires_at=guard.clock.now() + timedelta(minutes=10),
    )
    return CallScope(
        lane="eval", batch_id="offline-manual-batch", authorization_id="offline-terminal", scenario_id="T01"
    )


def dispatcher(repo: PostgresRepository, guard: QuotaGuard, handler: Any) -> tuple[AgentDispatcher, Any]:
    port = member_port(guard, handler)
    runtime = AgentRuntime(repo, port, SyntheticMeter(), offline=True)
    return AgentDispatcher(SimpleNamespace(repo=repo, runtime=runtime)), port


@pytest.mark.parametrize("lane", ["eval", "probe"])
def test_missing_manual_authority_survives_executor_and_is_zero_post(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, lane: str
) -> None:
    worker, port = dispatcher(p2_repo, wire_guard, lambda _: pytest.fail("no physical POST"))
    run = queued(p2_repo)
    try:
        with call_scope(CallScope(lane=lane, scenario_id="T01")):
            assert worker.tick() == 1
            worker.active[run["id"]].result(timeout=5)
        assert port.request_count == 0 and rows(wire_guard) == []
    finally:
        worker.close()
    assert current_scope() == CallScope()


def test_eval_tick_and_next_ordinary_tick_do_not_share_authority(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard
) -> None:
    seen: list[CallScope] = []

    def answer(_: httpx.Request) -> httpx.Response:
        seen.append(current_scope())
        return response()

    worker, port = dispatcher(p2_repo, wire_guard, answer)
    try:
        first = queued(p2_repo)
        with call_scope(manual_scope(wire_guard)):
            assert worker.tick() == 1
            worker.active[first["id"]].result(timeout=5)
        second = queued(p2_repo)
        assert worker.tick() == 1
        worker.active[second["id"]].result(timeout=5)
    finally:
        worker.close()
    assert port.request_count == 2 and [scope.lane for scope in seen] == ["eval", "interactive"]
    assert seen[0].authorization_id == "offline-terminal" and seen[1].authorization_id is None
    assert [row["run_id"] for row in rows(wire_guard)] == [first["id"], second["id"]]
    assert wire_guard.status()["in_flight"] == 0 and current_scope() == CallScope()


@pytest.mark.parametrize("change", ["expired", "stopped"])
def test_expired_manual_batch_or_stopped_account_never_posts_from_worker(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, change: str
) -> None:
    scope = manual_scope(wire_guard)
    if change == "stopped":
        wire_guard.record_stop("access_terminated")
    else:
        with wire_guard.store.connect() as connection, connection.transaction():
            connection.execute(
                sql.SQL("UPDATE {} SET expires_at=now()-interval '1 second'").format(
                    wire_guard.store.table("core_model_batches")
                )
            )
    worker, port = dispatcher(p2_repo, wire_guard, lambda _: pytest.fail("no physical POST"))
    run = queued(p2_repo)
    try:
        with call_scope(scope):
            assert worker.tick() == 1
            worker.active[run["id"]].result(timeout=5)
        assert port.request_count == 0 and rows(wire_guard) == [] and wire_guard.status()["in_flight"] == 0
    finally:
        worker.close()


@pytest.mark.parametrize("lane", ["eval", "probe"])
def test_long_lived_dispatcher_cannot_capture_temporary_grant(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, lane: str
) -> None:
    worker, _ = dispatcher(p2_repo, wire_guard, lambda _: pytest.fail("no physical POST"))
    try:
        with call_scope(CallScope(lane=lane)), pytest.raises(EvidenceError):
            worker.start()
        assert worker.thread is None and rows(wire_guard) == []
    finally:
        worker.close()


@pytest.mark.parametrize("change", ["cancel", "lease", "epoch"])
def test_expired_or_cancelled_identity_is_rejected_before_http(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, change: str
) -> None:
    repo = p2_repo
    run = repo.claim_run("alice", queued(repo)["id"])
    if change == "cancel":
        DispatcherCancellation(repo).request("alice", run["id"])
    else:
        with repo.transaction("alice") as connection:
            assignment = "lease_until=now()-interval '1 second'" if change == "lease" else "retry_epoch=retry_epoch+1"
            connection.execute(
                sql.SQL("UPDATE {} SET " + assignment + " WHERE id=%s").format(repo.table("core_runs")), (run["id"],)
            )
    port = member_port(wire_guard, lambda _: pytest.fail("no physical POST"))
    with pytest.raises(CoreError), member_run_scope(repo, run, role="primary"):
        port.complete([])
    assert port.request_count == 0 and rows(wire_guard) == []


def test_nested_scope_preserves_manual_authority_and_never_reads_request_fields(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard
) -> None:
    repo = p2_repo
    run = repo.claim_run("alice", queued(repo, lane="background")["id"])
    with repo.transaction("alice") as connection:
        connection.execute(
            sql.SQL("UPDATE {} SET request=request||%s WHERE id=%s").format(repo.table("core_runs")),
            (Jsonb({"lane": "interactive", "role": "critic", "authorization_id": "invented"}), run["id"]),
        )
    port = member_port(wire_guard, lambda _: response())
    with call_scope(CallScope(lane="interactive")), member_run_scope(repo, run, role="primary"):
        assert current_scope().lane == "background"
        with member_run_scope(repo, run, role="primary"):
            port.complete([])
    assert (rows(wire_guard)[0]["lane"], rows(wire_guard)[0]["role"]) == ("background", "primary")
    scope = manual_scope(wire_guard)
    critic = member_port(wire_guard, lambda _: response(), role="critic")
    with call_scope(scope), member_run_scope(repo, run, role="primary"):
        with member_run_scope(repo, run, role="critic"):
            critic.complete([], role="critic")
        assert current_scope().authorization_id == scope.authorization_id
    assert rows(wire_guard)[1]["lane"] == "eval" and rows(wire_guard)[1]["bucket"] == "critic"
    assert current_scope() == CallScope()


def test_background_parent_cannot_expand_to_interactive_run(p2_repo: PostgresRepository) -> None:
    run = p2_repo.claim_run("alice", queued(p2_repo)["id"])
    with (
        call_scope(CallScope(lane="background")),
        pytest.raises(EvidenceError),
        member_run_scope(p2_repo, run, role="primary"),
    ):
        pytest.fail("scope expanded")


@pytest.mark.parametrize("role", ["evaluation", "background"])
def test_observed_primary_does_not_borrow_another_bound_port_role(
    p2_repo: PostgresRepository, wire_guard: QuotaGuard, role: str
) -> None:
    run = p2_repo.claim_run("alice", queued(p2_repo)["id"])
    port = member_port(wire_guard, lambda _: pytest.fail("no physical POST"), role=role)
    control = RunControl(p2_repo, run, LoopPolicy())
    with pytest.raises(ConfigError):
        ObservedPort(port, control, lambda _: None).complete([])
    assert port.request_count == 0 and rows(wire_guard) == []

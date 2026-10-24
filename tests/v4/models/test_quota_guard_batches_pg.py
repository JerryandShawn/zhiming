"""Batch grants bind real ledger admissions without starting a model call."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardConfigurationError, GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock

from .test_quota_guard_pg import configure_central, post


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def begin(guard: QuotaGuard, batch: str = "batch-1", auth: str = "manual-start-1", **kwargs: Any) -> None:
    guard.begin_batch(
        batch_id=batch,
        authorization_id=auth,
        scenario_ids=kwargs.get("scenarios", ["S01", "S02"]),
        expires_at=kwargs.get("expires", guard.clock.now() + timedelta(minutes=15)),
    )


def evaluated(guard: QuotaGuard, attempt: str, **kwargs: Any) -> list[int]:
    values = dict(batch_id="batch-1", authorization_id="manual-start-1", scenario_id="S01")
    values.update(kwargs)
    return post(guard, attempt, role="evaluation", lane="eval", **values)


@pytest.mark.parametrize("lane", ["eval", "probe"])
def test_eval_and_probe_require_current_explicit_batch_before_reserving(central: dict[str, Any], lane: str) -> None:
    guard = QuotaGuard(**central)
    with pytest.raises(GuardRejected) as caught:
        post(guard, "not-authorized", role="evaluation", lane=lane)
    assert caught.value.kind == "manual_start_required"
    assert guard.status()["window"]["total"] == guard.status()["in_flight"] == 0


@pytest.mark.parametrize("scenarios", [[], ["S01"] * 2, [f"S{i:02}" for i in range(11)]])
def test_batch_at_most_ten_different_scenarios(central: dict[str, Any], scenarios: list[str]) -> None:
    guard = QuotaGuard(**central)
    with pytest.raises(GuardConfigurationError):
        begin(guard, scenarios=scenarios)
    assert guard.status()["window"]["total"] == 0


def test_target_and_judge_and_probe_count_each_post_with_same_grant(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    assert evaluated(guard, "target") == [1]
    assert post(
        guard,
        "judge",
        role="critic",
        lane="eval",
        batch_id="batch-1",
        authorization_id="manual-start-1",
        scenario_id="S01",
    ) == [1]
    assert post(
        guard,
        "probe",
        role="evaluation",
        lane="probe",
        batch_id="batch-1",
        authorization_id="manual-start-1",
        scenario_id="S02",
    ) == [1]
    state = guard.status()["window"]
    assert (state["total"], state["evaluation"], state["background"], state["critic"]) == (3, 3, 2, 1)


@pytest.mark.parametrize(
    "changed,kind",
    [
        ({"authorization_id": "invented"}, "manual_start_required"),
        ({"scenario_id": "S03"}, "batch_conflict"),
        ({"batch_id": "batch-other"}, "manual_start_required"),
    ],
)
def test_caller_cannot_change_granted_identity(central: dict[str, Any], changed: dict[str, str], kind: str) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    with pytest.raises(GuardRejected) as caught:
        evaluated(guard, "wrong-identity", **changed)
    assert caught.value.kind == kind and guard.status()["window"]["total"] == 0


def test_stable_grant_replays_but_cannot_extend_or_change_batch(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    begin(guard)
    begin(guard)
    for kwargs in (
        {"expires": clock.now() + timedelta(minutes=16)},
        {"scenarios": ["S03"]},
        {"batch": "another-batch"},
    ):
        with pytest.raises(GuardRejected):
            begin(guard, **kwargs)
    assert evaluated(guard, "original") == [1]


def test_expired_authorization_requires_new_explicit_grant_after_restart(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    begin(guard)
    clock.advance(timedelta(minutes=15))
    restarted = QuotaGuard(**central, clock=clock)
    with pytest.raises(GuardRejected) as caught:
        evaluated(restarted, "expired")
    assert caught.value.kind == "authorization_expired"
    begin(restarted, auth="manual-start-renewed")
    assert evaluated(restarted, "renewed", authorization_id="manual-start-renewed") == [1]


def test_twenty_minute_gap_survives_restart_and_one_use_authorization(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    begin(guard)
    evaluated(guard, "completed")
    guard.finish_batch("batch-1", "manual-start-1")
    guard.finish_batch("batch-1", "manual-start-1")
    restarted = QuotaGuard(**central, clock=clock)
    with pytest.raises(GuardRejected) as caught:
        begin(restarted, batch="batch-2", auth="manual-start-2")
    assert caught.value.kind == "batch_cooldown"
    clock.advance(timedelta(minutes=20))
    with pytest.raises(GuardRejected):
        begin(restarted, batch="batch-2", auth="manual-start-1")
    assert restarted.status()["window"]["total"] == 1
    begin(restarted, batch="batch-2", auth="manual-start-2")
    assert evaluated(restarted, "next-batch", batch_id="batch-2", authorization_id="manual-start-2") == [1]


def test_stop_invalidates_batch_and_clear_never_grants_calls(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    guard.record_stop("access_terminated")
    guard.clear_stop(authorization_id="explicit-clear")
    with pytest.raises(GuardRejected) as caught:
        evaluated(guard, "old-batch-cannot-resume")
    assert caught.value.kind == "authorization_expired"
    begin(guard, auth="user-explicitly-started-again")
    assert evaluated(guard, "new-start", authorization_id="user-explicitly-started-again") == [1]


def test_finish_rejects_in_flight_then_allows_finally_complete(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    with guard.acquire(
        "evaluation",
        "eval",
        attempt_id="running",
        provider="synthetic",
        model="k3-256k",
        batch_id="batch-1",
        authorization_id="manual-start-1",
        scenario_id="S01",
    ):
        with pytest.raises(GuardRejected) as caught:
            guard.finish_batch("batch-1", "manual-start-1")
        assert caught.value.kind == "in_flight_limit"
    guard.finish_batch("batch-1", "manual-start-1")
    with pytest.raises(GuardRejected):
        evaluated(guard, "closed-batch")


def test_interactive_cannot_attach_eval_grant(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    with pytest.raises(GuardConfigurationError):
        post(guard, "spoofed", batch_id="batch-1", authorization_id="manual-start-1", scenario_id="S01")
    assert guard.status()["window"]["total"] == 0


def test_stale_manual_clear_cannot_expire_new_grant_or_clear_new_stop(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    guard.record_stop("access_terminated")
    guard.clear_stop(authorization_id="clear-once")
    begin(guard, auth="new-manual-start")
    guard.clear_stop(authorization_id="clear-once")
    assert evaluated(guard, "new-grant-preserved", authorization_id="new-manual-start") == [1]
    guard.record_stop("concurrency_limited")
    guard.clear_stop(authorization_id="clear-once")
    assert guard.status()["stop_kind"] == "concurrency_limited"
    with pytest.raises(GuardRejected):
        guard.clear_stop(authorization_id="new-manual-start")


def test_noop_manual_clear_cannot_be_replayed_to_clear_future_stop(central: dict[str, Any]) -> None:
    guard = QuotaGuard(**central)
    begin(guard)
    guard.clear_stop(authorization_id="clear-before-any-stop")
    assert evaluated(guard, "noop-preserves-active-batch") == [1]
    guard.record_stop("access_terminated")
    guard.clear_stop(authorization_id="clear-before-any-stop")
    assert guard.status()["stop_kind"] == "access_terminated"

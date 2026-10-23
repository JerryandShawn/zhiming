"""Real isolated PG plus MockTransport; no real provider or server is contacted."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

import httpx
import pytest

from mingjing_core.models.errors import ModelUnavailable
from mingjing_core.models.quota_delegated import (
    begin_delegated_batch,
    resume_delegated,
)
from mingjing_core.models.quota_delegated_session import (
    DelegatedSession,
    require_active,
)
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_mode import current_delegated_session
from mingjing_core.models.quota_runtime import CallScope, call_scope, current_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, SystemClock, get_clock, set_clock

from .test_delegated_policy import CANDIDATE, NOW, synthetic_approval
from .test_quota_guard_pg import configure_central, post
from .test_quota_http_pg import adapter, answer, rows


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    def deny(*args: Any, **kwargs: Any) -> None:
        pytest.fail("real provider transport forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    return configure_central(p2_repo, monkeypatch)


def session_for(central: dict[str, Any], *, phase: str = "core", equivalent: bool | None = True) -> DelegatedSession:
    guard = QuotaGuard(**central, clock=FrozenClock(NOW))
    approval = synthetic_approval(equivalent)
    return DelegatedSession(guard, approval, phase=phase, scenario_ids=["synthetic-a", "synthetic-b"])


def scoped_receipt(receipt: dict[str, Any], scenario: str = "synthetic-a") -> CallScope:
    return CallScope(
        lane="eval",
        batch_id=receipt["batch_id"],
        authorization_id=receipt["authorization_id"],
        scenario_id=scenario,
    )


def test_more_than_eighty_requests_rotate_batches_without_stopping_later_interactive(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    port = adapter(session.guard, lambda _: answer())
    original = CallScope(lane="eval", run_id="leased-real-run", scenario_id="synthetic-a")
    with session.activate(), call_scope(original):
        assert require_active() is session
        for _ in range(81):
            assert port.complete([]).text == "合成"
            assert current_scope() is original
        snapshot = session.snapshot()
    assert current_delegated_session() is None
    with pytest.raises(GuardRejected):
        require_active()
    usage = rows(session.guard)
    counts = sorted(Counter(row["batch_id"] for row in usage).values())
    assert counts == [1] + [10] * 8
    assert snapshot["batches_started"] == 9 and snapshot["batch_requests"] == 1
    assert all(row["scenario_id"] == "synthetic-a" and row["run_id"] == "leased-real-run" for row in usage)
    assert session.guard.status()["window"]["total"] == 81
    assert session.guard.status()["remaining_total"] == 80
    session.close()
    assert post(session.guard, "normal-after-delegation") == [1]
    assert session.guard.status()["remaining_total"] == 79 and session.guard.status()["stop_kind"] is None


def test_physical_eleventh_attempt_cannot_reuse_a_batch(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    receipt = begin_delegated_batch(
        session.guard,
        session.approval,
        phase="core",
        batch_id="bounded",
        scenario_ids=["synthetic-a"],
    )
    port = adapter(session.guard, lambda _: answer())
    with call_scope(scoped_receipt(receipt)):
        for _ in range(10):
            port.complete([])
        with pytest.raises(GuardRejected) as caught:
            port.complete([])
    assert caught.value.kind == "batch_request_limit" and port.request_count == len(rows(session.guard)) == 10


def test_equivalence_is_capped_across_batch_rollover_and_restarts(
    central: dict[str, Any],
) -> None:
    session = session_for(central, phase="equivalence", equivalent=None)
    port = adapter(session.guard, lambda _: answer())
    with session.activate(), call_scope(session.scope("synthetic-a")):
        for _ in range(20):
            port.complete([])
        with pytest.raises(GuardRejected) as caught:
            port.complete([])
    assert caught.value.kind == "delegation_request_limit" and port.request_count == 20
    assert all(row["lane"] == "probe" for row in rows(session.guard))
    session.close()
    fresh = session_for(central, phase="equivalence", equivalent=None)
    with (
        fresh.activate(),
        call_scope(fresh.scope("synthetic-a")),
        pytest.raises(GuardRejected),
    ):
        adapter(fresh.guard, lambda _: pytest.fail("no twenty-first HTTP")).complete([])


def test_manual_prefix_forgery_and_model_retagging_are_rejected(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    fake = f"v7d-{CANDIDATE}-core-k3-256k-" + "b" * 32
    with pytest.raises(GuardRejected):
        session.guard.begin_batch(
            batch_id="forged",
            scenario_ids=["synthetic-a"],
            authorization_id=fake,
            expires_at=NOW + timedelta(minutes=10),
        )
    with (
        call_scope(
            CallScope(
                lane="eval",
                batch_id="forged",
                authorization_id=fake,
                scenario_id="synthetic-a",
            )
        ),
        pytest.raises(GuardRejected),
    ):
        adapter(session.guard, lambda _: pytest.fail("no forged HTTP")).complete([])
    begin_delegated_batch(
        session.guard,
        session.approval,
        phase="core",
        batch_id="immutable",
        scenario_ids=["synthetic-a"],
    )
    other = synthetic_approval(False)
    with pytest.raises(GuardRejected):
        begin_delegated_batch(
            session.guard,
            other,
            phase="core",
            batch_id="immutable",
            scenario_ids=["synthetic-a"],
        )
    assert rows(session.guard) == []


@pytest.mark.parametrize(
    "status,message,kind",
    [
        (403, "Synthetic permission denied", "permission_error"),
        (429, "You've reached your 5-hour usage limit.", "quota_5h"),
        (429, "usage limit", "quota"),
        (503, "Access terminated", "access_terminated"),
        (429, "concurrency_limited", "concurrency_limited"),
    ],
)
def test_terminal_errors_stop_every_lane_without_retry_or_raw_body(
    central: dict[str, Any], status: int, message: str, kind: str
) -> None:
    session = session_for(central)
    sent = []

    def handle(_: httpx.Request) -> httpx.Response:
        sent.append(1)
        return httpx.Response(status, json={"error": {"type": "permission_error", "message": message}})

    with session.activate(), call_scope(session.scope("synthetic-a")):
        with pytest.raises(ModelUnavailable):
            adapter(session.guard, handle).complete([])
        with pytest.raises(GuardRejected):
            adapter(session.guard, handle).complete([])
    assert sent == [1] and rows(session.guard)[0]["status"] == kind
    assert session.guard.status()["stop_kind"] == kind and session.guard.status()["resume_at"] is None
    with pytest.raises(GuardRejected):
        post(session.guard, "interactive-after-stop")
    assert "Synthetic permission denied" not in str(rows(session.guard))


def test_known_reset_uses_admission_clock_and_expired_grants_do_not_revive(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    before = get_clock()
    set_clock(FrozenClock(NOW - timedelta(days=400)))
    try:
        port = adapter(
            session.guard,
            lambda _: httpx.Response(
                429,
                headers={"Retry-After": "18000"},
                json={
                    "error": {
                        "type": "permission_error",
                        "message": "5-hour usage limit",
                    }
                },
            ),
        )
        with (
            session.activate(),
            call_scope(session.scope("synthetic-a")),
            pytest.raises(ModelUnavailable),
        ):
            port.complete([])
        assert session.guard.status()["resume_at"] == NOW + timedelta(hours=5)
        with pytest.raises(GuardRejected):
            resume_delegated(session.guard, session.approval)
        session.guard.clock.advance(timedelta(hours=5))
        assert resume_delegated(session.guard, session.approval)
        assert not resume_delegated(session.guard, session.approval)
        assert port.request_count == 1
        # A new batch is required; old reservations remain charged.
        with session.activate(), call_scope(session.scope("synthetic-a")):
            adapter(session.guard, lambda _: answer()).complete([])
        assert len(rows(session.guard)) == 2
    finally:
        set_clock(before)


@pytest.mark.parametrize("kind", ["quota_5h", "quota_weekly", "quota_monthly", "quota", "access_terminated"])
def test_unknown_reset_and_access_never_automatically_clear(central: dict[str, Any], kind: str) -> None:
    session = session_for(central)
    session.guard.record_stop(kind)
    session.guard.clock.advance(timedelta(days=1))
    with pytest.raises(GuardRejected) as caught:
        resume_delegated(session.guard, session.approval)
    assert caught.value.kind == kind and session.guard.status()["resume_at"] is None


def test_nonterminal_transient_is_not_randomly_retried_under_delegation(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    port = adapter(session.guard, lambda _: httpx.Response(503))
    with (
        session.activate(),
        call_scope(session.scope("synthetic-a")),
        pytest.raises(ModelUnavailable),
    ):
        port.complete([])
    assert port.request_count == len(rows(session.guard)) == 1
    assert session.guard.status()["stop_kind"] is None


def test_session_preserves_single_eval_slot_and_global_two_slots(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    receipt = begin_delegated_batch(
        session.guard,
        session.approval,
        phase="core",
        batch_id="slots",
        scenario_ids=["synthetic-a"],
    )
    args = dict(
        provider="kimi_code",
        model="k3-256k",
        batch_id=receipt["batch_id"],
        authorization_id=receipt["authorization_id"],
        scenario_id="synthetic-a",
        timeout=0,
    )
    with session.guard.acquire("primary", "eval", attempt_id="holding-eval", **args):
        with (
            pytest.raises(GuardRejected) as caught,
            session.guard.acquire("critic", "eval", attempt_id="second-eval", **args),
        ):
            pytest.fail("eval must be single flight")
        assert caught.value.kind == "in_flight_limit"
        with session.guard.acquire(
            "primary",
            "interactive",
            attempt_id="interactive",
            provider="kimi_code",
            model="k3",
        ):
            assert session.guard.status()["in_flight"] == 2
            with (
                pytest.raises(GuardRejected),
                session.guard.acquire(
                    "primary",
                    "interactive",
                    attempt_id="third",
                    provider="kimi_code",
                    model="k3",
                    timeout=0,
                ),
            ):
                pytest.fail("global must remain two")


def test_session_rejects_wrong_clock_freeze_scope_model_and_guard(
    central: dict[str, Any],
) -> None:
    session = session_for(central)
    with pytest.raises(GuardRejected):
        session_for(central, equivalent=None)
    port = adapter(session.guard, lambda _: pytest.fail("no invalid HTTP"))
    with session.activate():
        for scope in (CallScope(), CallScope(lane="eval", scenario_id="unplanned")):
            with call_scope(scope), pytest.raises(GuardRejected):
                port.complete([])
        with call_scope(session.scope("synthetic-a")), pytest.raises(GuardRejected):
            adapter(QuotaGuard(**central, clock=session.guard.clock), lambda _: answer()).complete([])
    old = get_clock()
    set_clock(FrozenClock(NOW - timedelta(days=400)))
    try:
        assert isinstance(QuotaGuard(**central).clock, SystemClock)
    finally:
        set_clock(old)
    assert rows(session.guard) == []

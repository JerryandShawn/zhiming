"""Central account budget and stop semantics use real, isolated PostgreSQL."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

import httpx
import pytest
from psycopg import sql

from mingjing_core.models.errors import ModelCancelled, ModelConcurrencyLimited, ModelPermissionDenied
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_store import QuotaStore
from mingjing_core.models.quota_types import (
    STOP_KINDS,
    GuardConfigurationError,
    GuardRejected,
    QuotaPolicy,
)
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock, get_clock


@pytest.fixture(name="central")
def central_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return configure_central(p2_repo, monkeypatch)


def configure_central(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    for name in (
        "KIMI_API_KEY",
        "MOONSHOT_API_KEY",
        "OPENAI_API_KEY",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    values = {
        "central_dsn": p2_repo.dsn,
        "central_schema": p2_repo.schema,
        "account_id": "synthetic-member",
        "ledger_identity": str(uuid.uuid4()),
    }
    provision(values)
    return values


def provision(values: dict[str, Any]) -> None:
    store = QuotaStore(
        values["central_dsn"],
        values["central_schema"],
        values["account_id"],
        values["ledger_identity"],
    )
    with store.connect() as connection, connection.transaction():
        store.provision(connection)


def post(
    guard: QuotaGuard,
    ident: str,
    *,
    role: str = "primary",
    lane: str = "interactive",
    **kwargs: Any,
) -> list[int]:
    sent: list[int] = []

    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(1)
        return httpx.Response(200, json={"ok": True})

    with (
        httpx.Client(transport=httpx.MockTransport(respond)) as client,
        guard.acquire(
            role,
            lane,
            attempt_id=ident,
            provider="synthetic",
            model="k3-256k",
            **kwargs,
        ) as attempt,
    ):
        client.post("https://synthetic.invalid/messages", json={"synthetic": True})
        attempt.result(
            usage={
                "input_tokens": 3,
                "output_tokens": 2,
                "private_body": "not-stored",
            }
        )
    return sent


def test_constructor_requires_existing_central_identity_and_does_not_bootstrap(
    central: dict[str, Any],
) -> None:
    for changed in (
        {"ledger_identity": str(uuid.uuid4())},
        {"account_id": "other-account"},
        {"central_schema": "undeployed_quota_schema"},
    ):
        with pytest.raises(GuardConfigurationError):
            QuotaGuard(**dict(central, **changed))
    guard = QuotaGuard(**central)
    assert guard.status()["remaining_total"] == 80


def test_interactive_can_borrow_but_eighty_first_post_is_denied_and_not_refunded(
    central: dict[str, Any],
) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    for index in range(80):
        assert post(guard, f"attempt-{index}") == [1]
    restarted = QuotaGuard(**central, clock=clock)
    with pytest.raises(GuardRejected) as caught:
        post(restarted, "attempt-80")
    assert caught.value.kind == "member_window_limit"
    state = restarted.status()
    assert state["window"]["total"] == 80 and state["remaining_total"] == state["in_flight"] == 0
    clock.advance(timedelta(hours=5))
    with pytest.raises(GuardRejected, match="会员调用"):
        post(restarted, "window-ended-still-stopped")
    restarted.clear_stop(authorization_id="manual-new-window")
    assert post(restarted, "later-window") == [1]


def test_critic_and_background_have_separate_non_borrowing_shares(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    for index in range(16):
        post(guard, f"background-{index}", role="background", lane="background")
        post(guard, f"critic-{index}", role="critic")
    assert not guard.background_allowed() and not guard.critic_allowed()
    for role, lane in (("background", "background"), ("critic", "interactive")):
        with pytest.raises(GuardRejected) as caught:
            post(guard, f"overflow-{role}", role=role, lane=lane)
        assert caught.value.kind == "share_limit"
    assert post(guard, "interactive-borrow") == [1]
    assert guard.status()["window"]["total"] == 33


@pytest.mark.parametrize("kind", sorted(STOP_KINDS))
def test_stop_is_persistent_for_new_connections_and_never_automatically_resumes(
    central: dict[str, Any], kind: str
) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    guard.record_stop(kind, resume_at=clock.now() + timedelta(hours=5) if kind == "quota_5h" else None)
    clock.advance(timedelta(days=8))
    restarted = QuotaGuard(**central, clock=clock)
    with pytest.raises(GuardRejected) as caught:
        post(restarted, "cannot-auto-resume")
    assert caught.value.kind == kind
    assert restarted.status()["stop_kind"] == kind and not restarted.status()["automatic_resume"]
    restarted.clear_stop(authorization_id="explicit-manual-clear")
    assert post(restarted, "after-manual-clear") == [1]


def test_concurrency_exception_stops_all_lanes_without_reducing_and_continuing(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    with (
        pytest.raises(ModelConcurrencyLimited),
        guard.acquire(
            "primary",
            "interactive",
            attempt_id="risk",
            provider="synthetic",
            model="k3-256k",
        ),
    ):
        raise ModelConcurrencyLimited()
    assert guard.status()["in_flight"] == 0 and guard.status()["stop_kind"] == "concurrency_limited"
    for role, lane in (
        ("primary", "interactive"),
        ("critic", "interactive"),
        ("background", "background"),
    ):
        with pytest.raises(GuardRejected) as caught:
            post(QuotaGuard(**central), "stop-" + role, role=role, lane=lane)
        assert caught.value.kind == "concurrency_limited"


def test_stop_can_escalate_and_five_hour_clear_is_never_early(
    central: dict[str, Any],
) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    guard.record_stop("quota_5h", resume_at=clock.now() + timedelta(hours=5))
    with pytest.raises(GuardRejected):
        guard.clear_stop(authorization_id="too-early")
    guard.record_stop("access_terminated")
    guard.record_stop("quota_5h")
    state = guard.status()
    assert state["stop_kind"] == "access_terminated" and state["resume_at"] is None


def test_exception_finally_releases_slot_and_retains_the_reservation(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    with (
        pytest.raises(RuntimeError, match="SYNTHETIC"),
        guard.acquire(
            "primary",
            "interactive",
            attempt_id="failed",
            provider="synthetic",
            model="k3-256k",
        ),
    ):
        assert guard.status()["in_flight"] == 1
        raise RuntimeError("SYNTHETIC_FAILURE")
    assert guard.status()["in_flight"] == 0 and guard.status()["window"]["total"] == 1
    with pytest.raises(GuardRejected) as caught:
        post(guard, "failed")
    assert caught.value.kind == "attempt_replayed"
    assert post(guard, "next") == [1]


def test_clock_rollback_fails_closed_without_reserving(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    post(guard, "first")
    clock.advance(-timedelta(seconds=1))
    with pytest.raises(GuardRejected) as caught:
        post(guard, "backwards")
    assert caught.value.kind == "clock_rollback"


def test_usage_is_body_free_and_unknown_tokens_are_null(
    central: dict[str, Any],
) -> None:
    guard = QuotaGuard(**central)
    post(guard, "usage")
    with guard.store.connect() as connection:
        row = connection.execute(sql.SQL("SELECT * FROM {}").format(guard.store.table("core_model_usage"))).fetchone()
    assert row["input_tokens"] == 3 and row["output_tokens"] == 2
    assert row["cache_read_tokens"] is None and row["cache_write_tokens"] is None
    assert "private_body" not in row and row["finished_at"] is not None and row["status"] == "ok"


def test_different_real_accounts_are_separate_but_business_run_ids_share_one_ledger(
    central: dict[str, Any],
) -> None:
    first = QuotaGuard(**central, policy=QuotaPolicy(max_calls=2))
    second = QuotaGuard(**central, policy=QuotaPolicy(max_calls=2))
    post(first, "business-a", run_id="business-a:run")
    post(second, "business-b", run_id="business-b:run")
    with pytest.raises(GuardRejected):
        post(second, "business-c")
    other = dict(central, account_id="another-real-account", ledger_identity=str(uuid.uuid4()))
    provision(other)
    assert post(QuotaGuard(**other), "other-account-attempt") == [1]


def test_observed_access_stop_survives_clock_rollback_during_http(central: dict[str, Any]) -> None:
    clock = FrozenClock(get_clock().now())
    guard = QuotaGuard(**central, clock=clock)
    with (
        pytest.raises(ModelPermissionDenied),
        guard.acquire("primary", "interactive", attempt_id="terminal", provider="synthetic", model="k3-256k"),
    ):
        clock.advance(-timedelta(seconds=5))
        raise ModelPermissionDenied(kind="access_terminated")
    clock.advance(timedelta(seconds=5))
    assert QuotaGuard(**central, clock=clock).status()["stop_kind"] == "access_terminated"


def test_waiting_background_can_be_cancelled_without_reservation(central: dict[str, Any]) -> None:
    guard, cancel = QuotaGuard(**central), threading.Event()
    with guard.acquire("background", "background", attempt_id="holding", provider="synthetic", model="k3-256k"):
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(
                post, QuotaGuard(**central), "waiting", role="background", lane="background", cancel_event=cancel
            )
            cancel.set()
            with pytest.raises(ModelCancelled):
                waiting.result(timeout=5)
        assert guard.status()["window"]["total"] == guard.status()["in_flight"] == 1
    assert guard.status()["in_flight"] == 0

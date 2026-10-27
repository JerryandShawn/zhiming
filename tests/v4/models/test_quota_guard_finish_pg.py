"""A failed real-PG finalization cannot replace stops or permit another POST."""

from __future__ import annotations

import traceback
from datetime import timedelta
from typing import Any

import httpx
import pytest

from mingjing_core.models.error_actions import MEMBER_PERMISSION_STOP, NEVER
from mingjing_core.models.errors import (
    ModelCancelled,
    ModelConcurrencyLimited,
    ModelPermissionDenied,
    ModelQuotaExhausted,
    ModelResponseIdentityError,
    ModelUnavailable,
)
from mingjing_core.models.quota_delegated import begin_delegated_batch
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit.clock import FrozenClock

from .test_delegated_policy import NOW, synthetic_approval
from .test_quota_guard_pg import configure_central
from .test_quota_http_pg import adapter, answer, rows

PRIVATE_MARKER = "synthetic_private_finish_marker"


class FalseyFailure(RuntimeError):
    def __bool__(self) -> bool:
        return False


@pytest.fixture(name="guard")
def guard_fixture(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> QuotaGuard:
    def deny(*args: Any, **kwargs: Any) -> None:
        pytest.fail("real provider HTTP is forbidden")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", deny)
    return QuotaGuard(**configure_central(p2_repo, monkeypatch), clock=FrozenClock(NOW))


def fail_finish(
    guard: QuotaGuard,
    monkeypatch: pytest.MonkeyPatch,
    control: BaseException | None = None,
) -> None:
    original = guard.store.finalizing

    def fail(connection: Any, now: Any) -> Any:
        result = original(connection, now)
        if control is not None:
            raise control
        # The real finish transaction rolls back, leaving the admitted row unfinished.
        connection.execute("SELECT synthetic_private_finish_marker()")
        return result

    monkeypatch.setattr(guard.store, "finalizing", fail)


def invoke(guard: QuotaGuard, error: BaseException | None, *, delegated: bool = False) -> None:
    scope: dict[str, Any] = {}
    if delegated:
        receipt = begin_delegated_batch(
            guard,
            synthetic_approval(),
            phase="core",
            batch_id="finish-test",
            scenario_ids=["synthetic-a"],
        )
        scope = {
            "batch_id": receipt["batch_id"],
            "authorization_id": receipt["authorization_id"],
            "scenario_id": "synthetic-a",
        }
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        guard.acquire(
            "primary",
            "eval" if delegated else "interactive",
            attempt_id="finish-attempt",
            provider="kimi_code",
            model="k3-256k",
            run_id="synthetic-run",
            **scope,
        ) as attempt,
    ):
        client.post("https://synthetic.invalid/messages", json={"synthetic": True})
        if error is not None:
            raise error
        attempt.result(usage={"input_tokens": 3})


def assert_retained(guard: QuotaGuard, *, unfinished: bool = True, status: str = "reserved") -> None:
    records = rows(guard)
    assert len(records) == 1 and records[0]["status"] == status
    assert (records[0]["finished_at"] is None) is unfinished
    state = guard.status()
    assert state["in_flight"] == 0 and state["window"]["total"] == 1
    expected_remaining = 80 if records[0]["batch_id"] is not None else 79
    assert state["stop_kind"] is None and state["remaining_total"] == expected_remaining


def assert_safe(error: BaseException) -> None:
    rendered = "".join(traceback.format_exception(error))
    if diagnostic := getattr(error, "safe_diagnostic", None):
        rendered += str(diagnostic())
    assert PRIVATE_MARKER not in rendered and "SYNTHETIC_NON_PROVIDER" not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__


@pytest.mark.parametrize("kind", ["success", "provider", "falsey"])
def test_without_finish_failure_existing_outcomes_are_unchanged(guard: QuotaGuard, kind: str) -> None:
    if kind == "success":
        invoke(guard, None)
        assert rows(guard)[0]["status"] == "ok" and guard.status()["in_flight"] == 0
        return
    original = ModelUnavailable() if kind == "provider" else FalseyFailure("SYNTHETIC")
    actions = getattr(original, "retry_actions", None)
    with pytest.raises(type(original)) as caught:
        invoke(guard, original)
    assert caught.value is original and getattr(caught.value, "retry_actions", None) is actions
    assert_retained(
        guard,
        unfinished=False,
        status="unavailable" if kind == "provider" else "unknown",
    )


@pytest.mark.parametrize("kind", ["quota_5h", "permission_error", "access_terminated", "concurrency_limited"])
def test_known_global_stop_survives_failed_finalization(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    if kind == "quota_5h":
        original = ModelQuotaExhausted(subtype=kind)
    elif kind == "concurrency_limited":
        original = ModelConcurrencyLimited()
    else:
        original = ModelPermissionDenied(
            kind=kind, retry_actions=MEMBER_PERMISSION_STOP if kind == "permission_error" else None
        )
    original.provider_reset_at = NOW + timedelta(hours=5) if kind == "quota_5h" else None
    actions, reset = original.retry_actions, original.provider_reset_at
    fail_finish(guard, monkeypatch)
    with pytest.raises(type(original)) as caught:
        invoke(guard, original, delegated=True)
    assert caught.value is original and original.kind == kind and original.global_stop
    assert original.retry_actions is actions and original.provider_reset_at is reset
    assert_safe(caught.value)
    assert_retained(guard)


@pytest.mark.parametrize("kind", ["cancelled", "keyboard", "exit", "generator"])
def test_original_cancellation_and_process_control_survive_finish_failure(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    original = {
        "cancelled": ModelCancelled(),
        "keyboard": KeyboardInterrupt(),
        "exit": SystemExit(),
        "generator": GeneratorExit(),
    }[kind]
    fail_finish(guard, monkeypatch)
    with pytest.raises(type(original)) as caught:
        invoke(guard, original, delegated=True)
    assert caught.value is original
    assert_safe(caught.value)
    assert_retained(guard)


def test_identity_stop_persists_when_physical_finalization_fails(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ModelResponseIdentityError()
    fail_finish(guard, monkeypatch)
    with pytest.raises(ModelResponseIdentityError) as caught:
        invoke(guard, original)
    assert caught.value is original and original.global_stop
    assert_safe(caught.value)
    records = rows(guard)
    assert len(records) == 1 and records[0]["status"] == "reserved" and records[0]["finished_at"] is None
    status = guard.status()
    assert status["stop_kind"] == "permission_error" and status["in_flight"] == 0
    assert status["window"]["total"] == 1
    with pytest.raises(GuardRejected) as stopped:
        invoke(guard, None)
    assert stopped.value.kind == "permission_error"
    assert len(rows(guard)) == 1


@pytest.mark.parametrize("broken_finish", [False, True])
def test_delegated_unknown_failure_keeps_existing_safe_normalization(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch, broken_finish: bool
) -> None:
    if broken_finish:
        fail_finish(guard, monkeypatch)
    original = FalseyFailure("SYNTHETIC_NON_PROVIDER")
    with pytest.raises(ModelUnavailable) as caught:
        invoke(guard, original, delegated=True)
    assert caught.value is not original and caught.value.kind == "unavailable"
    assert caught.value.retry_actions is NEVER and "SYNTHETIC_NON_PROVIDER" not in str(caught.value)
    assert_safe(caught.value)
    assert_retained(
        guard,
        unfinished=broken_finish,
        status="reserved" if broken_finish else "unknown",
    )


def test_provider_failure_and_unconfirmed_finish_cannot_retry(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_finish(guard, monkeypatch)
    port = adapter(guard, lambda _: httpx.Response(503))
    with pytest.raises(ModelUnavailable) as caught:
        port.complete([])
    assert caught.value.kind == "unavailable" and caught.value.retry_actions is NEVER
    assert port.request_count == 1
    assert_safe(caught.value)
    assert_retained(guard)


def test_successful_http_with_unconfirmed_finish_fails_closed_without_retry(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_finish(guard, monkeypatch)
    port = adapter(guard, lambda _: answer())
    with pytest.raises(GuardRejected) as caught:
        port.complete([])
    assert caught.value.kind == "ledger_unavailable" and caught.value.retry_actions is NEVER
    assert port.request_count == 1
    assert_safe(caught.value)
    assert_retained(guard)


def test_ordinary_body_failure_with_unconfirmed_finish_has_only_safe_guard_error(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch
) -> None:
    fail_finish(guard, monkeypatch)
    original = FalseyFailure("SYNTHETIC_NON_PROVIDER")
    with pytest.raises(GuardRejected) as caught:
        invoke(guard, original)
    assert caught.value.kind == "ledger_unavailable" and caught.value.retry_actions is NEVER
    assert "SYNTHETIC_NON_PROVIDER" not in str(caught.value)
    assert_safe(caught.value)
    assert_retained(guard)


@pytest.mark.parametrize("kind", ["success", "provider", "quota", "cancelled", "keyboard"])
def test_finish_process_control_yields_only_to_an_original_termination(
    guard: QuotaGuard, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    original = {
        "success": None,
        "provider": ModelUnavailable(),
        "quota": ModelQuotaExhausted(subtype="quota_5h"),
        "cancelled": ModelCancelled(),
        "keyboard": KeyboardInterrupt(),
    }[kind]
    finishing = KeyboardInterrupt("SYNTHETIC_FINISH_INTERRUPT")
    expected = original if kind in {"quota", "cancelled", "keyboard"} else finishing
    fail_finish(guard, monkeypatch, finishing)
    with pytest.raises(type(expected)) as caught:
        invoke(guard, original)
    assert caught.value is expected
    assert_safe(caught.value)
    assert_retained(guard)

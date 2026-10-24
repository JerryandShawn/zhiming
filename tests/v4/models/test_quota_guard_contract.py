"""Pure configuration and safe diagnostics; no DB or real network."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from mingjing_core.models.quota_guard import Attempt
from mingjing_core.models.quota_types import (
    STOP_KINDS,
    GuardConfigurationError,
    GuardRejected,
    QuotaPolicy,
    bucket,
    instant,
)


@pytest.mark.parametrize(
    "changed",
    [
        dict(max_calls=81),
        dict(max_calls=True),
        dict(max_calls=0),
        dict(eval_max_calls=81),
        dict(eval_max_calls=False),
        dict(window=timedelta(hours=4)),
        dict(window=None),
        dict(batch_gap=timedelta(minutes=19)),
        dict(batch_gap="20"),
        dict(interactive_share=float("nan")),
        dict(critic_share=float("inf")),
        dict(background_share=True),
        dict(background_share=-0.2),
        dict(background_share=0.3),
    ],
)
def test_policy_cannot_relax_limits_or_accept_ambiguous_values(changed: dict[str, Any]) -> None:
    with pytest.raises(GuardConfigurationError):
        QuotaPolicy(**changed)


@pytest.mark.parametrize(
    "role,lane", [("unknown", "interactive"), ("primary", "unknown"), ("background", "interactive")]
)
def test_invalid_role_or_background_borrow_is_denied(role: str, lane: str) -> None:
    with pytest.raises(GuardConfigurationError):
        bucket(role, lane)


@pytest.mark.parametrize("kind", sorted(STOP_KINDS))
def test_all_central_stops_have_no_retry_no_fallback_and_manual_clear(kind: str) -> None:
    error = GuardRejected(kind)
    assert error.kind == kind and error.global_stop
    assert error.retry_actions.persistent_stop and error.retry_actions.manual_clear
    assert error.retry_actions.retry == "never" and error.retry_actions.fallback == "none"
    assert "kind" in error.safe_diagnostic()


@pytest.mark.parametrize("value", [None, True, -1, 2**63, 3.5, "7"])
def test_unknown_or_invalid_token_usage_is_null_without_body(value: Any) -> None:
    receipt = Attempt("synthetic")
    receipt.result(usage={"input_tokens": value, "request_body": "not-stored"})
    assert receipt.usage == dict(input_tokens=None, cache_read_tokens=None, cache_write_tokens=None, output_tokens=None)


def test_naive_time_and_unknown_result_kind_are_rejected() -> None:
    with pytest.raises(GuardConfigurationError):
        instant(datetime(2026, 10, 18))
    with pytest.raises(GuardConfigurationError):
        Attempt("synthetic").result(kind="untrusted-private-error")

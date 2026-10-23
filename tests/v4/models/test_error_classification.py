"""Synthetic U37 contracts classify without HTTP, retries, PG or raw diagnostics."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import httpx
import pytest

from mingjing_core.domain.consultation import ModelUnavailable as LegacyUnavailable
from mingjing_core.models import errors
from mingjing_core.models.error_actions import ErrorActions
from mingjing_core.models.error_classification import classify_error
from mingjing_core.models.provider_diagnostics import permission_quota, public_quota_message

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[3] / "tools/eval/fixtures/u37_error_matrix.json").read_text(encoding="utf-8")
)
CASES = FIXTURE["cases"]
DIAGNOSTIC_KEYS = {
    "code",
    "reason",
    "failure_code",
    "usage",
    "usage_known",
    "provider_http_status",
    "latency_seconds",
    "stop_reason",
    "tool_count",
    "kind",
    "provider_error_type",
    "provider_message",
    "quota_subtype",
    "http_status",
}


def _classify(case: dict[str, Any]) -> errors.ModelUnavailable:
    entry = case["input"]
    return classify_error(entry["status"], entry["body"], membership=entry["membership"], surface=entry["surface"])


def _public_surfaces(error: errors.ModelUnavailable) -> str:
    return json.dumps(error.safe_diagnostic(), ensure_ascii=False) + str(error) + repr(error.args) + repr(vars(error))


@pytest.mark.parametrize("case", CASES, ids=lambda row: row["id"])
def test_u37_http_sse_matrix(case: dict[str, Any]) -> None:
    expected = case["expected"]
    failure = _classify(case)
    assert type(failure) is getattr(errors, expected["exception"])
    assert isinstance(failure, LegacyUnavailable)
    assert failure.kind == expected["kind"]
    assert failure.provider_http_status == case["input"]["status"]
    assert failure.provider_error_type == expected["provider_error_type"]
    assert failure.provider_message == expected["public_message"]
    assert failure.retry_actions.max_attempts == expected["max_attempts"]
    assert failure.retry_actions.delays_seconds == tuple(expected["delays_seconds"])
    assert failure.retry_actions.fallback == expected["fallback"]
    assert failure.global_stop == failure.retry_actions.global_stop == expected["global_stop"]
    assert failure.retry_actions.persistent_stop == expected["persistent_stop"]
    assert failure.__cause__ is None and failure.__context__ is None
    diagnostic = failure.safe_diagnostic()
    assert set(diagnostic) <= DIAGNOSTIC_KEYS
    assert diagnostic["kind"] == expected["kind"]
    assert all(marker not in _public_surfaces(failure) for marker in expected["never_include"])
    assert not {"request", "response", "payload", "body"}.intersection(vars(failure))
    if case["input"]["surface"] == "sse":
        assert "http_status" not in diagnostic and "provider_http_status" not in diagnostic


@pytest.mark.parametrize("surface,status", [("http", 403), ("sse", None)])
@pytest.mark.parametrize("message", ["Too many concurrent requests", "Concurrent request limit", "并发请求受限"])
def test_concurrency_signal_is_persistent_all_stop(surface: str, status: int | None, message: str) -> None:
    # Nonrecorded wording is a format assumption, not a claimed provider capture.
    failure = classify_error(
        status, {"error": {"type": "permission_error", "message": message}}, membership=True, surface=surface
    )
    assert isinstance(failure, errors.ModelConcurrencyLimited)
    assert failure.kind == "concurrency_limited"
    assert failure.global_stop and failure.retry_actions.persistent_stop and failure.retry_actions.manual_clear
    assert failure.retry_actions.max_attempts == 1 and failure.retry_actions.fallback == "none"


@pytest.mark.parametrize("surface,status", [("http", 429), ("sse", None)])
def test_nonmembership_insufficient_quota_uses_strict_type(surface: str, status: int | None) -> None:
    failure = classify_error(
        status,
        {"error": {"type": "insufficient_quota", "message": "SYNTHETIC_PRIVATE"}},
        membership=False,
        surface=surface,
    )
    assert isinstance(failure, errors.ModelQuotaExhausted)
    assert failure.kind == failure.quota_subtype == "quota"
    assert failure.retry_actions.max_attempts == 1
    assert failure.retry_actions.fallback == "configured_nonmembership"
    assert not failure.global_stop and not failure.retry_actions.persistent_stop
    assert "SYNTHETIC_PRIVATE" not in _public_surfaces(failure)


@pytest.mark.parametrize("error_type", ["insufficient_quota", "permission_error", None, "unknown"])
def test_membership_429_is_rate_limited_even_with_quota_words(error_type: str | None) -> None:
    failure = classify_error(
        429, {"error": {"type": error_type, "message": "synthetic quota usage limit"}}, membership=True
    )
    assert type(failure) is errors.ModelRateLimited
    assert failure.kind == "rate_limited" and not failure.global_stop
    assert failure.retry_actions.max_attempts == 4 and failure.retry_actions.delays_seconds == (1, 3, 9)


@pytest.mark.parametrize("error_type", [None, "other_error", [], {}])
def test_nonmembership_unknown_quota_words_do_not_replace_type(error_type: object) -> None:
    payload = {"error": {"type": error_type, "message": "SYNTHETIC_ECHO quota usage limit"}}
    http = classify_error(429, payload, membership=False)
    stream = classify_error(None, payload, membership=False, surface="sse")
    assert isinstance(http, errors.ModelRateLimited) and http.kind == "rate_limited"
    assert type(stream) is errors.ModelUnavailable and stream.retry_actions.max_attempts == 1
    assert "SYNTHETIC_ECHO" not in _public_surfaces(http) + _public_surfaces(stream)


@pytest.mark.parametrize("status", [400, 401, 403, 500, None, True])
def test_nonmembership_insufficient_type_cannot_override_other_http_status(status: object) -> None:
    failure = classify_error(
        status, {"error": {"type": "insufficient_quota", "message": "synthetic"}}, membership=False
    )
    assert not isinstance(failure, errors.ModelQuotaExhausted)
    assert not failure.global_stop


@pytest.mark.parametrize("status", [400, 403, 429, 500, None])
@pytest.mark.parametrize("signal", ["access_terminated", "concurrency_limited"])
def test_explicit_d1_type_has_priority_without_echoing_text(status: int | None, signal: str) -> None:
    failure = classify_error(
        status,
        {"error": {"type": signal, "message": "SYNTHETIC_PRIVATE_D1"}},
        membership=True,
        surface="sse" if status is None else "http",
    )
    assert failure.kind == signal
    assert failure.global_stop and failure.retry_actions.persistent_stop
    assert failure.retry_actions.manual_clear and failure.retry_actions.max_attempts == 1
    assert "SYNTHETIC_PRIVATE_D1" not in _public_surfaces(failure)


@pytest.mark.parametrize("subtype", ["quota", "quota_5h", "quota_weekly", "quota_monthly"])
def test_quota_constructor_aliases_and_legacy_code(subtype: str) -> None:
    previous = errors.ModelQuotaExhausted(subtype=subtype)
    current = errors.ModelQuotaExhausted(kind=subtype)
    assert previous.kind == current.kind == previous.quota_subtype == current.quota_subtype == subtype
    assert current.code == "MODEL_QUOTA_EXHAUSTED" and current.global_stop
    assert current.safe_diagnostic()["quota_subtype"] == subtype
    assert isinstance(current, LegacyUnavailable)


def test_quota_conflict_has_no_untrusted_value_in_exception() -> None:
    with pytest.raises(ValueError, match="Conflicting model error classification") as caught:
        errors.ModelQuotaExhausted(subtype="quota_weekly", kind="SYNTHETIC_PRIVATE_KIND")
    assert "SYNTHETIC_PRIVATE_KIND" not in str(caught.value)


def test_permission_alias_and_payload_subclass_preserve_old_handlers() -> None:
    assert errors.ModelPermissionError is errors.ModelPermissionDenied
    assert errors.ModelPermissionError().code == "MODEL_PERMISSION_DENIED"
    assert isinstance(errors.ModelConcurrencyLimited(), errors.ModelPermissionDenied)
    assert isinstance(errors.ModelPayloadTooLarge(), errors.ModelBadRequest)
    assert isinstance(errors.ModelContentFiltered(), errors.ModelBadRequest)


@pytest.mark.parametrize(
    "error_class,kind",
    [
        (errors.ModelCancelled, "cancelled"),
        (errors.CapabilityError, "capability_error"),
        (errors.ModelProtocolError, "protocol_error"),
    ],
)
def test_old_special_errors_keep_their_kind_and_action(error_class: type[errors.ModelUnavailable], kind: str) -> None:
    failure = error_class("SYNTHETIC_PRIVATE_MESSAGE")
    assert failure.kind == kind
    assert failure.retry_actions.max_attempts == (2 if kind == "protocol_error" else 1)
    assert "SYNTHETIC_PRIVATE_MESSAGE" not in _public_surfaces(failure)
    if kind == "protocol_error":
        assert failure.reason == "json" and failure.failure_code == "MODEL_JSON"


def test_actions_are_immutable_and_unknown_sse_never_retry() -> None:
    failure = classify_error(None, {"error": {"type": "unknown", "message": "quota"}}, membership=True, surface="sse")
    assert isinstance(failure.retry_actions, ErrorActions) and failure.retry_actions.max_attempts == 1
    with pytest.raises(FrozenInstanceError):
        failure.retry_actions.max_attempts = 100
    assert errors.ModelUnavailable().retry_actions.max_attempts == 4


def test_constructor_rejects_uncontrolled_kinds_and_error_types() -> None:
    failure = errors.ModelUnavailable(
        kind="SYNTHETIC_PRIVATE_KIND", error_type="SYNTHETIC_PRIVATE_TYPE", provider_message="SYNTHETIC_PRIVATE_MESSAGE"
    )
    assert failure.kind == "unavailable" and failure.provider_error_type is None and failure.provider_message is None
    assert "SYNTHETIC_PRIVATE" not in _public_surfaces(failure)


def test_public_sentence_extraction_never_exports_echo_prefix() -> None:
    sentence = "You've reached your monthly usage limit for this billing cycle."
    body = f"SYNTHETIC_PREFIX {'Z' * 600} {sentence} SYNTHETIC_SUFFIX"
    assert public_quota_message(body) == sentence
    assert permission_quota({"error": {"type": "permission_error", "message": body}}) == ("quota_monthly", sentence)
    assert public_quota_message("月额度已用完 SYNTHETIC_CHINESE_ECHO") is None


def test_classification_never_creates_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Pure classification must not construct an HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden)
    for case in CASES:
        _classify(case)


def test_nonstring_provider_fields_are_not_stringified() -> None:
    class CannotStringify:
        def __str__(self) -> str:
            raise AssertionError("Untrusted object must not be stringified")

    failure = classify_error(403, {"error": {"type": CannotStringify(), "message": CannotStringify()}}, membership=True)
    assert type(failure) is errors.ModelPermissionDenied and failure.provider_message is None


def test_nonmembership_payment_error_keeps_legacy_nonretry_contract() -> None:
    failure = classify_error(402, {"error": {"type": "billing_error", "message": "synthetic"}}, membership=False)
    assert isinstance(failure, errors.ModelBadRequest)
    assert failure.retry_actions.max_attempts == 1 and failure.retry_actions.fallback == "none"
    assert not failure.global_stop

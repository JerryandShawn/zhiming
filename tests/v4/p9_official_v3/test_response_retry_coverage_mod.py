"""Malformed response metadata never turns an unknown effect into a confirmed safe retry."""

import pytest

from mingjing_core.adapters.channels.cardkit_official_v3 import classify_response

from .isolated_coverage_mod import isolated_p9 as isolated_p9


@pytest.mark.parametrize("code", [99991400.0, "99991400", True, None, float("nan"), float("inf")])
def test_noninteger_body_code_cannot_assert_a_known_not_executed_rate_refusal(code: object) -> None:
    result = classify_response(400, code)
    assert result.status == "uncertain"
    assert result.after_ms == 0 and result.action_required is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", 0),
        ("0.0001", 1),
        ("1.0001", 1001),
        ("1.25", 1250),
        ("86400", 86400000),
        ("-1", 1000),
        ("86401", 1000),
        ("NaN", 1000),
        ("Infinity", 1000),
        ("-Infinity", 1000),
        ("", 1000),
        ("not-a-number", 1000),
        (None, 1000),
    ],
)
def test_rate_delay_is_finite_bounded_seconds_rounded_up_to_milliseconds(raw: object, expected: int) -> None:
    for status, code in ((429, None), (400, 99991400)):
        result = classify_response(status, code, {"X-OgW-RaTeLiMiT-ReSeT": raw})
        assert result.status == "retryable" and result.reason == "rate_limited"
        assert result.after_ms == expected


def test_http_429_is_independent_explicit_rate_evidence_but_5xx_and_network_unknown_take_precedence() -> None:
    assert classify_response(429, 99991400.0).status == "retryable"
    for status, code, network in ((500, 99991400, False), (503, 10002, False), (429, 99991400, True)):
        result = classify_response(status, code, {"x-ogw-ratelimit-reset": "30"}, network_error=network)
        assert result.status == "uncertain" and result.after_ms == 0


@pytest.mark.parametrize("status", [None, True, 400.0, "400"])
def test_noninteger_status_is_unknown_even_when_the_body_looks_like_a_permanent_refusal(status: object) -> None:
    result = classify_response(status, 10002)
    assert result.status == "uncertain" and result.after_ms == 0


def test_unknown_or_duplicate_uuid_does_not_inherit_a_retry_delay_from_headers() -> None:
    for code in (200770, 300120, 123456):
        result = classify_response(400, code, {"x-ogw-ratelimit-reset": "86400"})
        assert result.status == "uncertain" and result.after_ms == 0

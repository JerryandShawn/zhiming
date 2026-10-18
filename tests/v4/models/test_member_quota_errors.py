"""Public membership errors are typed; private provider echoes are discarded."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.domain.consultation import ModelUnavailable as LegacyUnavailable
from mingjing_core.models.anthropic_messages import AnthropicMessages
from mingjing_core.models.errors import ModelPermissionDenied, ModelQuotaExhausted
from mingjing_core.models.provider_diagnostics import public_quota_message
from mingjing_core.models.transport import http_error
from tools.eval.quota import ProviderStopped, QuotaGuard, provider_stop_reason

from .test_protocols import adapter, recording

FIXTURES = json.loads(
    (Path(__file__).resolve().parents[3] / "tools/eval/fixtures/member_quota_public.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("subtype", ["quota_5h", "quota_weekly"])
@pytest.mark.parametrize("protocol", [None, AnthropicMessages])
def test_member_403_is_one_attempt_and_diagnostic_is_public(subtype: str, protocol: Any) -> None:
    body = FIXTURES[subtype]

    def factory(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json=body)

    model = adapter(factory, protocol, settings={"membership": True}) if protocol else adapter(factory)
    with pytest.raises(ModelQuotaExhausted) as caught:
        model.complete([])
    diagnostic = caught.value.safe_diagnostic()
    assert diagnostic["http_status"] == diagnostic["provider_http_status"] == 403
    assert diagnostic["provider_error_type"] == "permission_error"
    assert diagnostic["quota_subtype"] == subtype
    assert diagnostic["provider_message"] == body["error"]["message"]
    assert model.request_count == model.quota_errors == 1
    assert provider_stop_reason(caught.value) == subtype


@pytest.mark.parametrize(
    "body",
    [
        {
            "error": {
                "type": "permission_error",
                "message": "Invalid permission; synthetic-private",
            }
        },
        {
            "error": {
                "type": "other_error",
                "message": "You've reached your 5-hour usage limit.",
            }
        },
        {"error": {"message": "You've reached your weekly (7-day) usage limit."}},
        {"error": {"type": {}, "message": "usage limit"}},
        {"echo": "quota; usage limit; synthetic-private"},
    ],
)
def test_other_403_is_permission_failure_not_quota(body: dict[str, Any]) -> None:
    failure = http_error(httpx.Response(403, json=body), membership=True)
    assert isinstance(failure, ModelPermissionDenied)
    assert not isinstance(failure, ModelQuotaExhausted)
    assert provider_stop_reason(failure) == "provider_http_error"
    assert "synthetic-private" not in json.dumps(failure.safe_diagnostic()) + str(failure)


def test_plain_or_invalid_403_stays_permission_failure() -> None:
    for message in (
        "usage limit",
        "You've reached your weekly (7-day) usage limit.",
        "{bad",
    ):
        assert isinstance(
            http_error(httpx.Response(403, text=message), membership=True),
            ModelPermissionDenied,
        )


def test_echoed_body_never_leaves_public_sentence_allowlist() -> None:
    public = FIXTURES["quota_5h"]["error"]["message"]
    message = "synthetic-private-user " + public + " synthetic-private-credential " + "x" * 500
    failure = http_error(
        httpx.Response(403, json={"error": {"type": "permission_error", "message": message}}),
        membership=True,
    )
    diagnostic = json.dumps(failure.safe_diagnostic())
    assert "private" not in diagnostic and failure.provider_message == public
    assert len(failure.provider_message) <= 240
    assert public_quota_message("Private content with usage limit") is None


@pytest.mark.parametrize("subtype", ["quota_5h", "quota_weekly"])
def test_legacy_v3_error_reaches_eval_guard_before_business_retry(subtype: str) -> None:
    model = ConfiguredModel(key="synthetic", base="https://synthetic.invalid", model="k3")
    guard = QuotaGuard(model, "target")
    requests: list[httpx.Request] = []
    original_client = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, json=FIXTURES[subtype])

    with patch(
        "mingjing_core.adapters.model.httpx.Client",
        side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    ):
        for _ in range(2):
            with pytest.raises(ProviderStopped) as caught:
                guard.generate(system="synthetic-private", payload={}, schema={}, purpose="intake")
            assert caught.value.reason == subtype
    assert len(requests) == guard.calls == 1


def test_legacy_other_403_keeps_http_reason_and_no_public_body() -> None:
    model = ConfiguredModel(key="synthetic", base="https://synthetic.invalid")
    with patch("mingjing_core.adapters.model.httpx.Client") as client:
        client.return_value.__enter__.return_value.post.return_value = httpx.Response(
            403,
            json={
                "error": {
                    "type": "permission_error",
                    "message": "synthetic-private permission",
                }
            },
        )
        with pytest.raises(LegacyUnavailable) as caught:
            model.generate(system="合成", payload={}, schema={}, purpose="intake")
    assert type(caught.value) is LegacyUnavailable
    assert caught.value.safe_diagnostic()["provider_http_status"] == 403
    assert "private" not in str(caught.value.safe_diagnostic())


@pytest.mark.parametrize("subtype", ["quota_5h", "quota_weekly"])
def test_streamed_public_member_error_retains_subtype_without_invented_status(
    subtype: str,
) -> None:
    model = adapter(lambda _: httpx.Response(200, content=recording({"type": "error", **FIXTURES[subtype]})))
    with pytest.raises(ModelQuotaExhausted) as caught:
        model.complete([])
    assert caught.value.quota_subtype == subtype
    assert "provider_http_status" not in caught.value.safe_diagnostic()

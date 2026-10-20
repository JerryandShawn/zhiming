"""Live membership preflight cannot infer a central ledger or trust model role fields."""

from __future__ import annotations

import httpx
import pytest

from mingjing_core.models.config_policy import ConfigError
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.quota_http import membership_endpoint
from mingjing_core.models.quota_runtime import (
    ENVIRONMENT,
    CallScope,
    CentralLocation,
    call_scope,
    current_scope,
)
from mingjing_core.models.quota_types import GuardRejected


def test_real_transport_missing_central_identity_has_zero_posts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ENVIRONMENT.values():
        monkeypatch.delenv(name, raising=False)
    calls = []
    monkeypatch.setattr(httpx.Client, "send", lambda *args, **kwargs: calls.append(1))
    port = OpenAICompat(
        base_url="https://api.kimi.com/coding/v1",
        api_key="synthetic",
        model="k3",
        provider="kimi_code",
    )
    with pytest.raises(GuardRejected) as error:
        port.complete([])
    assert error.value.kind == "ledger_unavailable" and calls == [] and port.request_count == 0


def test_scope_is_restored_and_never_loaded_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEMBER_LANE", "interactive")
    original = current_scope()
    with call_scope(CallScope(lane="eval", batch_id="synthetic-batch")):
        assert current_scope().lane == "eval"
    assert current_scope() == original


def test_central_location_does_not_fall_back_to_business_database() -> None:
    with pytest.raises(GuardRejected):
        CentralLocation.from_environment({"ZHIMING_DATABASE_URL": "postgresql://synthetic.invalid/private"})
    location = CentralLocation("private-dsn", "central", "member", "id")
    assert "private-dsn" not in repr(location)


def test_member_endpoint_cannot_lose_guard_by_omitting_settings() -> None:
    assert membership_endpoint("https://api.kimi.com/coding/v1")
    assert membership_endpoint("https://synthetic.invalid", "kimi_code")
    assert not membership_endpoint("https://api.moonshot.cn/v1")


def test_model_role_parameter_cannot_change_trusted_constructed_binding() -> None:
    port = OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="k3",
        provider="kimi_code",
        transport=httpx.MockTransport(lambda _: pytest.fail("must not send")),
    )
    with pytest.raises(ConfigError, match="可信构造"):
        port.complete([], role="critic")
    assert port.request_count == 0

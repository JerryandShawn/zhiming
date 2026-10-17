"""Quota control crosses real PostgreSQL and LangGraph; only the model is replaced."""

import os
from datetime import datetime
from typing import Any

import pytest

from mingjing_core.domain.consultation import ModelUnavailable
from mingjing_core.timekit import FrozenClock, get_clock, set_clock
from tests.test_core_pg_channels import FixtureModel
from tools.eval.quota import ProviderStopped
from tools.eval.targets.v3_target import V3Target


class QuotaProvider:
    def __init__(self, error: Exception) -> None:
        self.calls: list[str] = []
        self.error = error

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs["purpose"])
        raise self.error


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ModelUnavailable(provider_http_status=429), "quota"),
        (ModelUnavailable(provider_http_status=403), "provider_http_error"),
    ],
)
def test_real_service_stops_at_first_request_and_blocks_repair(error: Exception, reason: str) -> None:
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable PostgreSQL 15")
    original = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    provider = QuotaProvider(error)
    target = V3Target(dsn=dsn, provider=provider)
    try:
        target.reset({"profile": "empty_profile", "_scenario_id": "T01"})
        result = target.send({"user": "今天几号", "channel": "web", "_index": 1})
        assert result.metadata["stop_reason"] == reason
        assert result.metadata["provider_http_status"] == error.provider_http_status
        assert result.metadata["error_category"] == "provider"
        assert result.model_calls == len(provider.calls) == 1
        assert provider.calls == ["intake"]
        with pytest.raises(ProviderStopped):
            target.model.generate(purpose="repair")
        assert target.model.calls == len(provider.calls) == 1
    finally:
        target.close()
        set_clock(original)


class QuotaDuringRepair(FixtureModel):
    def __init__(self, status: int) -> None:
        super().__init__()
        self.status = status
        self.calls: list[str] = []

    def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs["purpose"])
        if kwargs["purpose"] == "repair":
            raise ModelUnavailable(reason="http", provider_http_status=self.status)
        result = super().generate(**kwargs)
        if kwargs["purpose"] == "synthesis":
            result["output"]["cited_fact_ids"] = ["synthetic-missing-fact"]
        return result


@pytest.mark.parametrize("status", [429, 403])
def test_quota_after_real_validation_enters_repair_still_stops_without_retry(status: int) -> None:
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable PostgreSQL 15")
    original = get_clock()
    set_clock(FrozenClock(datetime.fromisoformat("2026-10-17T10:30:00+08:00")))
    provider = QuotaDuringRepair(status)
    target = V3Target(dsn=dsn, provider=provider)
    try:
        target.reset({"profile": "empty_profile", "_scenario_id": "T01"})
        result = target.send({"user": "今天几号", "channel": "web", "_index": 1})
        assert provider.calls == ["intake", "synthesis", "repair"]
        assert result.model_calls == len(provider.calls) == 3
        assert result.metadata["stop_reason"] == ("quota" if status == 429 else "provider_http_error")
        assert result.metadata["provider_http_status"] == status
        with pytest.raises(ProviderStopped):
            target.model.generate(purpose="repair")
        assert target.model.calls == len(provider.calls) == 3
    finally:
        target.close()
        set_clock(original)

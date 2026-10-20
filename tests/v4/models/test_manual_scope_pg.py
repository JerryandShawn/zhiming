"""An evaluator's receipt and role reach the physical central PG admission boundary."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_runtime import ENVIRONMENT, CentralLocation
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.repositories.postgres import PostgresRepository
from mingjing_core.timekit import clock as clock_module
from mingjing_core.timekit.clock import FrozenClock, SystemClock
from tools.manual_grant import load_manual_grant, scoped_scenario
from tools.manual_grant_io import write_private_receipt
from tools.member_start import grant_batch

from .test_quota_guard_pg import configure_central
from .test_quota_http_pg import answer, rows


def setup(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    values = configure_central(p2_repo, monkeypatch)
    for key, name in ENVIRONMENT.items():
        monkeypatch.setenv(name, values[key])
    return values


def port() -> OpenAICompat:
    class Substitute(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            return answer()

    return OpenAICompat(
        base_url="https://synthetic.invalid",
        api_key="synthetic",
        model="k3-256k",
        provider="kimi_code",
        settings={"role_binding": "evaluation"},
        transport=Substitute(),
    )


def test_active_e1_receipt_survives_scenario_clock_and_records_eval_role(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    values = setup(p2_repo, monkeypatch)
    guard = CentralLocation.from_environment().guard()
    receipt = tmp_path / "receipt.json"
    write_private_receipt(receipt, grant_batch(guard, "E1", 1, ["T01"]))
    monkeypatch.setenv("MEMBER_GRANT_RECEIPT", str(receipt))
    monkeypatch.setenv("MEMBER_EVAL_SUITE", "E1")

    @scoped_scenario
    def evaluate(scenario: Any) -> str:
        monkeypatch.setattr(clock_module, "_clock", FrozenClock(datetime(2026, 10, 17, tzinfo=UTC)))
        return port().complete([], role="evaluation").text

    assert evaluate(SimpleNamespace(id="T01")) == "合成"
    record = rows(QuotaGuard(**values))[0]
    assert (record["lane"], record["role"], record["scenario_id"]) == (
        "eval",
        "evaluation",
        "T01",
    )
    assert record["batch_id"] == load_manual_grant(receipt, "E1", ["T01"]).batch_id
    assert abs((record["at"] - SystemClock().now()).total_seconds()) < 10


def test_missing_authority_stops_before_substituted_physical_http(
    p2_repo: PostgresRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = setup(p2_repo, monkeypatch)
    monkeypatch.delenv("MEMBER_GRANT_RECEIPT", raising=False)

    @scoped_scenario
    def evaluate(scenario: Any) -> str:
        return port().complete([], role="evaluation").text

    with pytest.raises(GuardRejected) as error:
        evaluate(SimpleNamespace(id="T01"))
    assert error.value.kind == "manual_start_required" and rows(QuotaGuard(**values)) == []

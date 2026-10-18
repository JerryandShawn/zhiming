"""Real isolated PostgreSQL retains safe quota metadata and one business charge."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.models.errors import ModelQuotaExhausted
from mingjing_core.timekit.clock import FrozenClock
from tests.test_core_pg_channels import FixtureModel
from tools.eval.member_budget import MemberBudget
from tools.eval.targets.v3_target import V3Target


@pytest.fixture
def member_target() -> Iterator[tuple[V3Target, ConfiguredModel]]:
    dsn = os.getenv("CORE_TEST_DSN")
    if not dsn:
        pytest.skip("requires disposable PostgreSQL 15")
    model = ConfiguredModel(key="synthetic-test-only", base="https://synthetic.invalid", model="synthetic-k3")
    target = V3Target(dsn=dsn, provider=model)
    target.reset({"profile": "empty_profile", "facts": [], "thread": [], "_scenario_id": "T01"})
    target.service.model = model
    try:
        yield target, model
    finally:
        target.close()


@pytest.mark.parametrize(
    "subtype,message",
    [
        ("quota_5h", "You've reached your 5-hour usage limit."),
        ("quota_weekly", "You've reached your weekly (7-day) usage limit."),
    ],
)
def test_legacy_service_quota_records_only_audited_public_diagnostic(
    member_target: Any, subtype: str, message: str
) -> None:
    target, _ = member_target
    requests: list[httpx.Request] = []
    original_client = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            403,
            json={"error": {"type": "permission_error", "message": message + " SYNTHETIC_PRIVATE_ECHO"}},
        )

    request = target.service.submit(
        owner=target.owner, message="合成供应商额度回执验收", request_id="member-quota-" + subtype
    )
    target.run_ids.append(request["id"])
    with (
        patch(
            "mingjing_core.adapters.model.httpx.Client",
            side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
        ),
        pytest.raises(ModelQuotaExhausted),
    ):
        target.service.execute(target.owner, request["id"])
    run = target.repo.fetch_run(target.owner, request["id"])
    diagnostics = target.repo.list(target.owner, "model_call")
    assert len(requests) == len(diagnostics) == run["calls"] == 1
    assert run["status"] == "failed" and not run["repair_used"]
    assert diagnostics[0]["quota_subtype"] == subtype
    assert diagnostics[0]["provider_error_type"] == "permission_error"
    assert diagnostics[0]["provider_message"] == message
    assert diagnostics[0]["provider_http_status"] == 403
    assert "SYNTHETIC_PRIVATE" not in json.dumps(diagnostics)


def test_langgraph_context_propagates_actual_request_meter(member_target: Any, tmp_path: Path) -> None:
    target, _ = member_target
    target.service.model = target.model
    budget = MemberBudget(tmp_path / "member.json", "pg-context", FrozenClock(datetime(2026, 10, 18, tzinfo=UTC)))
    target.model.provider.budget = budget
    budget.before_batch(["T01"])
    fixture = FixtureModel()
    requests: list[httpx.Request] = []
    original_client = httpx.Client

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        schema = body["tools"][0]["input_schema"]
        payload = json.loads(body["messages"][0]["content"][0]["text"])
        purpose = "intake" if "plan" in schema["properties"] else "synthesis"
        result = fixture.generate(system="合成", payload=payload, schema=schema, purpose=purpose)
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "submit", "input": result["output"]}],
                "stop_reason": "tool_use",
            },
        )

    with patch(
        "mingjing_core.adapters.model.httpx.Client",
        side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    ):
        result = target.send({"user": "请陪我整理今天一个小行动。", "_index": 1})
    assert result.error is None and result.text
    assert len(requests) == budget.snapshot()["run_calls_by_role"]["target"] == 2
    assert budget.snapshot()["real_calls_by_role"] == {"target": 2, "judge": 0, "probe": 0}

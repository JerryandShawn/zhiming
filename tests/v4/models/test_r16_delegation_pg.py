"""R16 admission uses isolated PostgreSQL and actual adapters with MockTransport."""

from __future__ import annotations

import json
from collections import Counter

import httpx
import pytest

from mingjing_core.models.quota_delegated_session import DelegatedSession
from mingjing_core.models.quota_guard import QuotaGuard
from mingjing_core.models.quota_r16 import connection_approval
from mingjing_core.models.quota_runtime import call_scope
from mingjing_core.models.quota_types import GuardRejected
from mingjing_core.timekit.clock import FrozenClock

from .test_delegated_policy import CANDIDATE, NOW
from .test_delegated_quota_pg import central_fixture as central_fixture  # noqa: F401
from .test_k31_first_release import registry
from .test_quota_http_pg import adapter, rows
from .test_r16_delegation import fixture_gate


def test_k31_connect_uses_exact_identity_and_twenty_total_across_rollover_and_restart(central: dict) -> None:
    guard = QuotaGuard(**central, clock=FrozenClock(NOW))
    approval = connection_approval(fixture_gate()[0], CANDIDATE, NOW)
    session = DelegatedSession(guard, approval, phase="k31-connect", scenario_ids=["synthetic-k31"])
    posted = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "k3.1-pro" and body["reasoning_effort"] == "high"
        posted.append(1)
        chunk = {
            "model": "k3.1-pro",
            "choices": [{"delta": {"content": "合成"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 2},
        }
        return httpx.Response(200, text="data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n")

    port = registry().resolve("primary")[0].adapter(guard=guard, transport=httpx.MockTransport(respond))
    with session.activate(), call_scope(session.scope("synthetic-k31")):
        # An old model cannot spend a K31 approval, even with a valid new batch.
        with pytest.raises(GuardRejected):
            adapter(guard, lambda _: pytest.fail("wrong identity must never POST")).complete([])
        for _ in range(20):
            assert port.complete([]).model == "k3.1-pro"
        with pytest.raises(GuardRejected) as stopped:
            port.complete([])
        assert stopped.value.kind == "delegation_request_limit"
    session.close()
    renewed = DelegatedSession(guard, approval, phase="k31-connect", scenario_ids=["synthetic-k31"])
    with renewed.activate(), call_scope(renewed.scope("synthetic-k31")), pytest.raises(GuardRejected):
        port.complete([])
    renewed.close()
    usage = rows(guard)
    assert len(posted) == port.request_count == len(usage) == 20
    assert sorted(Counter(row["batch_id"] for row in usage).values()) == [10, 10]
    assert all(row["model"] == "k3.1-pro" and row["lane"] == "probe" for row in usage)
    assert guard.status()["stop_kind"] is None

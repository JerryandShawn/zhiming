"""Physical-time budgets cover actual HTTP attempts across roles and processes."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock, patch

import httpx
import pytest

from mingjing_core.adapters.model import ConfiguredModel
from mingjing_core.models.legacy import PortBackedModel
from mingjing_core.timekit.clock import FrozenClock
from tools.eval.member_budget import MemberBudget
from tools.eval.quota import ProviderStopped, QuotaGuard

from .test_protocols import adapter
from .test_schema_registry import registry


def setup_budget(tmp_path: Path, run_id: str = "baseline") -> tuple[MemberBudget, FrozenClock]:
    clock = FrozenClock(datetime(2026, 10, 18, 1, 0, tzinfo=UTC))
    return MemberBudget(tmp_path / "membership.json", run_id, clock), clock


def test_rolling_cap_combines_all_roles_and_new_runs_cannot_reset_it(
    tmp_path: Path,
) -> None:
    budget, clock = setup_budget(tmp_path)
    budget.before_batch(["T01"])
    for index in range(80):
        budget.before_provider_request(("target", "judge", "probe")[index % 3])
    with pytest.raises(ProviderStopped) as caught:
        budget.before_provider_request("target")
    assert caught.value.reason == "member_window_limit"
    assert caught.value.resume_at == "2026-10-18T06:00:00+00:00"
    snapshot = budget.snapshot()
    assert snapshot["real_calls_total"] == snapshot["window_calls_total"] == 80
    assert snapshot["real_calls_by_role"] == {"target": 27, "judge": 27, "probe": 26}
    sibling = MemberBudget(budget.path, "new-run", clock)
    with pytest.raises(ProviderStopped, match="stopped"):
        sibling.before_provider_request("probe")
    assert sibling.snapshot()["real_calls_total"] == 80
    clock.advance(timedelta(hours=5))
    budget.before_provider_request("target")
    assert budget.snapshot()["window_calls_total"] == 1


def test_batch_size_and_shared_twenty_minute_gap(tmp_path: Path) -> None:
    budget, clock = setup_budget(tmp_path)
    with pytest.raises(ValueError):
        budget.before_batch([f"T{index:02}" for index in range(11)])
    budget.before_batch(["T01", "T02"])
    budget.before_batch(["T01", "T02"])
    with pytest.raises(ValueError):
        budget.before_batch(["T03"])
    sibling = MemberBudget(budget.path, "another-run", clock)
    with pytest.raises(ValueError):
        sibling.before_batch(["T03"])
    budget.finish_batch()
    with pytest.raises(ProviderStopped) as caught:
        sibling.before_batch(["T03"])
    assert caught.value.reason == "batch_cooldown" and caught.value.resume_at.endswith("01:20:00+00:00")
    clock.advance(timedelta(minutes=20))
    sibling.before_batch(["T03"])
    assert sibling.snapshot()["active_batch"] == ["T03"]


def test_quota_five_hour_stop_resumes_once_then_second_stop_requires_user(
    tmp_path: Path,
) -> None:
    budget, clock = setup_budget(tmp_path)
    budget.before_batch(["T01"])
    budget.before_provider_request("target")
    budget.record_stop("quota_5h", 403)
    budget.record_stop("quota_5h", 403)
    assert budget.snapshot()["quota_5h_stops"] == 1
    assert budget.snapshot()["resume_at"] == "2026-10-18T06:00:00+00:00"
    with pytest.raises(ProviderStopped):
        budget.resume_once()
    clock.advance(timedelta(hours=5))
    restored = MemberBudget(budget.path, "baseline", clock)
    with pytest.raises(ProviderStopped):
        restored.before_provider_request("target")
    restored.resume_once()
    restored.before_batch(["T01"])
    restored.before_provider_request("target")
    restored.record_stop("quota_5h", 403)
    clock.advance(timedelta(days=1))
    with pytest.raises(ProviderStopped):
        restored.resume_once()
    state = restored.snapshot()
    assert state["quota_5h_stops"] == 2 and state["auto_resumes"] == 1 and state["resume_at"] is None


def test_weekly_stops_every_run_and_never_auto_resumes(tmp_path: Path) -> None:
    budget, clock = setup_budget(tmp_path)
    budget.record_stop("quota_weekly", 403)
    clock.advance(timedelta(days=30))
    sibling = MemberBudget(budget.path, "new-run", clock)
    with pytest.raises(ProviderStopped) as caught:
        sibling.before_provider_request("probe")
    assert caught.value.reason == "quota_weekly" and caught.value.resume_at is None
    with pytest.raises(ProviderStopped):
        budget.resume_once()
    assert sibling.snapshot()["warning"] == "线上可能受影响"


def test_concurrent_reservations_across_budget_instances_never_exceed_eighty(
    tmp_path: Path,
) -> None:
    budget, clock = setup_budget(tmp_path)

    def reserve(index: int) -> bool:
        instance = MemberBudget(budget.path, f"probe-{index}", clock)
        try:
            instance.before_provider_request("probe")
            return True
        except ProviderStopped:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(reserve, range(100)))
    assert sum(results) == budget.snapshot()["real_calls_total"] == 80


def test_clock_rollback_and_malformed_ledger_fail_before_reservation(
    tmp_path: Path,
) -> None:
    budget, clock = setup_budget(tmp_path)
    budget.before_provider_request("probe")
    clock.advance(timedelta(seconds=-1))
    with pytest.raises(ValueError, match="会员时钟"):
        budget.before_provider_request("probe")
    assert budget.snapshot()["real_calls_total"] == 1
    budget.path.write_text("invalid-json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="账本无效"):
        budget.before_provider_request("probe")
    assert budget.path.read_text(encoding="utf-8") == "invalid-json"


def test_legacy_http_failure_counts_once_and_guard_stops_before_next_post(
    tmp_path: Path,
) -> None:
    budget, _ = setup_budget(tmp_path)
    budget.before_batch(["T01"])
    guard = QuotaGuard(
        ConfiguredModel(key="synthetic", base="https://synthetic.invalid"),
        "target",
        budget,
    )
    public = {
        "error": {
            "type": "permission_error",
            "message": "You've reached your 5-hour usage limit.",
        }
    }
    original_client = httpx.Client
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(403, json=public)

    with patch(
        "mingjing_core.adapters.model.httpx.Client",
        side_effect=lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    ):
        for _ in range(2):
            with pytest.raises(ProviderStopped) as caught:
                guard.generate(system="合成", payload={}, schema={}, purpose="intake")
            assert caught.value.resume_at == "2026-10-18T06:00:00+00:00"
    assert budget.snapshot()["run_calls_by_role"] == {
        "target": 1,
        "judge": 0,
        "probe": 0,
    }
    assert len(requests) == 1


def test_new_port_retries_and_failover_share_the_actual_request_cap(
    tmp_path: Path,
) -> None:
    budget, _ = setup_budget(tmp_path)
    budget.before_batch(["T01"])
    for _ in range(77):
        budget.before_provider_request("probe")
    shim = PortBackedModel(registry(tmp_path))
    adapters: list[Any] = []

    def factory(_: Any) -> Any:
        model = adapter(lambda _: httpx.Response(503), max_retries=3)
        adapters.append(model)
        return model

    shim.port = shim.registry.port(factory=factory)
    guard = QuotaGuard(shim, "target", budget)
    with pytest.raises(ProviderStopped) as caught:
        guard.generate(system="合成", payload={}, schema={}, purpose="intake")
    assert caught.value.reason == guard.stop_reason == "member_window_limit"
    assert sum(model.request_count for model in adapters) == 3
    assert budget.snapshot()["real_calls_total"] == 80
    assert budget.snapshot()["run_calls_by_role"]["target"] == 3
    ledger = json.loads(budget.path.read_text(encoding="utf-8"))
    assert all(set(call) == {"at", "role", "run_id"} for call in ledger["calls"])


@pytest.mark.parametrize("reason", ["quota_5h", "quota_weekly"])
def test_preflight_shared_stop_is_kept_for_target_result_metadata(tmp_path: Path, reason: str) -> None:
    budget, _ = setup_budget(tmp_path)
    budget.before_batch(["T01"])
    provider = Mock()
    guard = QuotaGuard(provider, "target", budget)
    budget.record_stop(reason, 403)
    with pytest.raises(ProviderStopped) as caught:
        guard.check_open()
    assert caught.value.reason == guard.stop_reason == reason
    assert guard.provider_http_status == 403
    provider.generate.assert_not_called()
    assert budget.snapshot()["real_calls_total"] == 0

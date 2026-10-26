"""Chart calculation stays outside PG locks and checks privacy again before saving."""

import pytest

from .test_computation_charts_pg import engine, legacy_profile as profile
from .test_toolkit_pg import setup
from .test_toolkit_pg import tool_repo as source_fixture
from .test_turn_sources_runtime_pg import intake


@pytest.fixture(name="chart_privacy_repo")
def repository(p2_repo, monkeypatch):
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def test_privacy_command_during_calculation_prevents_artifacts_claims_and_cache(chart_privacy_repo):
    repo = chart_privacy_repo
    ingress, thread = intake(repo)
    profile(repo)
    harness = setup(repo, "请看看合成八字")
    calls = []

    def optout():
        # The test engine asserts that no outer PG transaction is held here.
        calls.append("calculated")
        ingress.receive(owner="alice", thread_id=thread, message="本轮别记", request_id="chart-optout")

    harness.service.charts = engine(repo, optout)
    result, _ = harness.call("chart_compute", {"system": "bazi", "target": "2026-10-17"})
    assert calls == ["calculated"] * 3  # Native approximate-time branches, no replayed calculation.
    assert result.ok is False and result.receipt == {"write_status": "stopped", "code": "privacy_optout"}
    assert repo.list("alice", "artifact") == [] and repo.list("alice", "interpretive_claim") == []
    assert not [row for row in repo.list("alice", "runtime_step") if row["id"].startswith("agent_chart_cache_")]

"""Real PG preparation/persistence and post-calculation fencing; no engine network."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

import pytest

from mingjing_core.adapters.charts import ChartAdapter
from mingjing_core.agent.tools.computation_parameters import ChartCompute
from mingjing_core.application.agent_tools_charts import ChartCalculationUnavailable, ChartInputsRequired, execute_chart
from mingjing_core.application.agent_tools_contracts import ToolContext, tool_input_fingerprint
from mingjing_core.application.charts_service import ChartsService
from mingjing_core.application.memory import MemoryService
from mingjing_core.domain.contracts import CoreError, EvidenceError, ScopeError
from mingjing_core.repositories.postgres import PostgresRepository
from tests.test_core_charts import fake_bazi

from .test_toolkit_pg import SAID_AT, Harness, setup
from .test_toolkit_pg import tool_repo as source_fixture


@pytest.fixture(name="tool_repo")
def repository(p2_repo: PostgresRepository, monkeypatch: pytest.MonkeyPatch) -> PostgresRepository:
    return source_fixture.__wrapped__(p2_repo, monkeypatch)


def profile(repo: PostgresRepository, *, precision: str = "exact") -> list[dict[str, Any]]:
    memory, facts = MemoryService(repo), []
    fields = {
        "gender": "男",
        "birth.solar_datetime": "2012-05-03 13:18",
        "birth.timezone_offset": 8,
        "birth.precision": precision,
        "birth.location.lng": 104.07,
        "birth.location.lat": 30.67,
    }
    if precision == "approximate":
        fields["birth.time_uncertainty_minutes"] = 1
    for field, value in fields.items():
        text = f"请保存我的{field}为{value}"
        source = memory.receive("alice", content=text, source_id=uuid.uuid4().hex, at=SAID_AT)
        facts.append(memory.save_fact("alice", "self", source["id"], text, "profile", field=field, value=value))
    return facts


def legacy_profile(repo: PostgresRepository) -> list[dict[str, Any]]:
    # Board42 D3 keeps uncertain-time sampling on the existing legacy path.
    return profile(repo, precision="approximate")


def context(h: Harness) -> tuple[dict[str, Any], ToolContext]:
    args = ChartCompute(system="bazi", target="2026-10-17").model_dump()
    step = h.journal.next_or_replay(
        h.run, kind="tool", name="chart_compute", input_fp=tool_input_fingerprint("chart_compute", args)
    )
    return args, ToolContext.from_step(step, thread_id="life:self", source_ids=(h.source["id"],))


def engine(repo: PostgresRepository, effect: Any = None) -> ChartsService:
    def runner(system: str, args: dict[str, Any]) -> dict[str, Any]:
        assert getattr(repo._local, "connection", None) is None
        if effect is not None:
            effect()
        return fake_bazi(args)

    return ChartsService(lambda owner: ChartAdapter(owner, runner=runner))


def test_chart_real_persistence_replay_and_explicit_legacy_limits(tool_repo: PostgresRepository) -> None:
    legacy_profile(tool_repo)
    h = setup(tool_repo, "请看看合成八字")
    args, ctx = context(h)
    calls = []
    charts = engine(tool_repo, lambda: calls.append("calculate"))
    result = execute_chart(h.service, args, ctx, charts=charts)
    assert result.ok and result.data["adapter_mode"] == "legacy_v3"
    assert "true_solar_time_basis" in result.data["unsupported_capabilities"]
    assert "boundary_alerts" in result.data["unsupported_capabilities"]
    assert "boundary_alerts" not in result.data["calculation"]
    records = result.data["persisted"]
    assert records["artifacts"] and records["claims"]
    original = tool_repo.get("alice", "artifact", records["artifacts"][0]["id"])
    assert original["artifact"]["owner_user_id"] == "alice" and original["run_id"] == h.run["id"]
    count = len(tool_repo.list("alice", "artifact"))
    repeated = execute_chart(h.service, args, ctx, charts=charts)
    assert repeated.data["persisted"] == records and len(tool_repo.list("alice", "artifact")) == count
    assert calls == ["calculate"] * 3  # Approximate input samples both endpoints and center once.


def test_missing_profile_and_incognito_do_not_invoke_calculator(tool_repo: PostgresRepository) -> None:
    h = setup(tool_repo, "请看看合成八字")
    args, ctx = context(h)
    with pytest.raises(ChartInputsRequired):
        execute_chart(h.service, args, ctx, charts=engine(tool_repo))
    legacy_profile(tool_repo)
    with pytest.raises(ScopeError):
        execute_chart(h.service, args, replace(ctx, incognito=True), charts=engine(tool_repo))
    assert tool_repo.list("alice", "artifact") == []


def test_outer_transaction_is_rejected_instead_of_holding_it_for_engine(tool_repo: PostgresRepository) -> None:
    legacy_profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    args, ctx = context(h)
    with tool_repo.transaction("alice"), pytest.raises(EvidenceError, match="外层"):
        execute_chart(h.service, args, ctx, charts=engine(tool_repo))


@pytest.mark.parametrize("change", ["cancel", "profile_change"])
def test_inflight_calculation_cannot_save_after_current_authority_changes(
    tool_repo: PostgresRepository,
    change: str,
) -> None:
    facts = legacy_profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    args, ctx = context(h)

    def effect() -> None:
        if change == "cancel":
            tool_repo.fail_run("alice", h.run["id"], "synthetic-cancel", h.run["lease_token"], status="cancelled")
        else:
            fact = facts[0]
            tool_repo.update("alice", "fact", fact["id"], {"value": "女"}, expected_revision=fact["revision"])

    with pytest.raises(CoreError):
        execute_chart(h.service, args, ctx, charts=engine(tool_repo, effect))
    assert tool_repo.list("alice", "artifact") == [] and tool_repo.list("alice", "interpretive_claim") == []


def test_private_engine_failure_is_sanitized_without_fake_result(tool_repo: PostgresRepository) -> None:
    legacy_profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    args, ctx = context(h)

    class FailedEngine:
        def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("PRIVATE-STDERR-BIRTH")

    with pytest.raises(ChartCalculationUnavailable) as error:
        execute_chart(h.service, args, ctx, charts=FailedEngine())
    assert "PRIVATE" not in str(error.value) and tool_repo.list("alice", "artifact") == []


@pytest.mark.parametrize("withdrawal", ["artifact", "profile_source", "current_source"])
def test_cached_calculation_cannot_resurrect_withdrawn_data(tool_repo: PostgresRepository, withdrawal: str) -> None:
    facts = legacy_profile(tool_repo)
    h = setup(tool_repo, "看看合成八字")
    args, ctx = context(h)
    result = execute_chart(h.service, args, ctx, charts=engine(tool_repo))
    if withdrawal == "artifact":
        record = result.data["persisted"]["artifacts"][0]
        tool_repo.delete("alice", "artifact", record["id"], expected_revision=record["revision"])
    elif withdrawal == "profile_source":
        fact = facts[0]
        MemoryService(tool_repo).retire_fact("alice", fact["id"], expected_revision=fact["revision"], scope="source")
    else:
        source = tool_repo.get("alice", "message", h.source["id"])
        tool_repo.delete("alice", "message", source["id"], expected_revision=source["revision"])
    with pytest.raises(CoreError):
        execute_chart(h.service, args, ctx, charts=engine(tool_repo))

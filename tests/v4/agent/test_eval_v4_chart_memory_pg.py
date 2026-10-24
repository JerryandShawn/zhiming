"""Six unchanged original contracts against real chart workers, PG and commit warnings."""

from __future__ import annotations

import os
import subprocess
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_chart_observations import chart_observations
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_observations import structural_observations
from tools.eval.targets.v4_target import V4Target

ROOT = Path(__file__).resolve().parents[3]
IDENTITIES = ("C01", "C03", "C07", "M02", "M06", "M12")


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    dsn, charts = os.getenv("CORE_TEST_DSN"), os.getenv("CHART_PYTHON")
    if not dsn:
        pytest.skip("requires disposable loopback PostgreSQL15")
    assert charts and Path(charts).is_file(), "explicit locked Charts interpreter required"
    worker = ROOT / "mingjing_core/adapters/charts/worker.py"
    run = subprocess.run

    # Charts invokes precisely four argv members; the whitelist intentionally
    # refuses shells and every unrelated child process.
    def charts_only(args, *values, **kwargs):
        assert isinstance(args, list) and len(args) == 4
        assert Path(args[0]).resolve() == Path(charts).resolve()
        assert args[1:3] == ["-X", "utf8"] and Path(args[3]).resolve() == worker.resolve()
        return run(args, *values, **kwargs)

    def reject(*args, **kwargs):
        raise AssertionError("offline chart/memory acceptance forbids provider or Feishu HTTP")

    monkeypatch.setattr(httpx.Client, "send", reject)
    monkeypatch.setattr(httpx.AsyncClient, "send", reject)
    monkeypatch.setattr(subprocess, "run", charts_only)
    value = V4Target(dsn=dsn)
    try:
        yield value
    finally:
        value.close()


@pytest.mark.parametrize("identity", IDENTITIES)
def test_six_original_contracts_observe_actual_effects(target: V4Target, identity: str) -> None:
    original = next(case for case in load_scenarios(ROOT / "tools/eval/scenarios") if case.id == identity)
    prepared = execution_overlay(original)
    assert scenario_contract_hash(prepared) == scenario_contract_hash(original)
    result = evaluate_scenario(prepared, target, target_name="v4")
    assert result["status"] == "passed", result["failed_assertions"]
    observed = target.inspect_db()
    if identity.startswith("C"):
        steps = observed["observed_tools"]
        assert any(step["name"] == "chart_compute" and step["output"]["ok"] for step in steps)
        artifacts = observed["artifact"]
        assert artifacts and all(row["run_id"] == target.run_ids[-1] for row in artifacts)
        assert observed["chart"]["source_store"] == "core_entities.artifact.data"
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        assert not chart_observations(artifacts, target.owner, dict(run, retry_epoch=run["retry_epoch"] + 1))
        assert not chart_observations(artifacts, "another-owner", run)
    elif identity == "M02":
        goals = [
            row["data"] for row in observed["entities"] if row["kind"] == "fact" and row["data"].get("kind") == "goal"
        ]
        assert len(goals) == 1 and "event_at" not in goals[0]
        assert goals[0]["said_at"] and goals[0]["source_refs"]
    elif identity == "M06":
        proposals = observed["proposal"]
        assert len(proposals) == 1 and proposals[0]["health"] is True
        assert proposals[0]["sensitivity"] == "third_party" and proposals[0]["source_refs"]
    else:
        run = target.repo.fetch_run(target.owner, target.run_ids[-1])
        semantic = structural_observations(run)
        assert semantic and semantic[0]["epoch"] == run["retry_epoch"]
        assert semantic[0]["source_store"] == "core_runs.result.meta.structural_warnings"
        wrong = deepcopy(run)
        wrong["result"]["meta"]["core_run"]["run_id"] = "another-run"
        assert not structural_observations(wrong)
        wrong = deepcopy(run)
        wrong["result"]["meta"]["structural_warnings"] = []
        assert not structural_observations(wrong)

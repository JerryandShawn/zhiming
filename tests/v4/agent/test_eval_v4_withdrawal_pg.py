"""Original F04 must observe real revocation and one clean Agent regeneration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval.engine import evaluate_scenario
from tools.eval.schema import load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as target_fixture


@pytest.fixture
def target(monkeypatch: pytest.MonkeyPatch):
    yield from target_fixture.__wrapped__(monkeypatch)


def test_f04_withdrawal_observes_one_new_epoch_without_restoring_private_body(target: V4Target) -> None:
    root = Path(__file__).resolve().parents[3]
    scenario = next(case for case in load_scenarios(root / "tools/eval/scenarios") if case.id == "F04")
    result = evaluate_scenario(execution_overlay(scenario), target, target_name="v4")
    assert result["status"] == "passed", result
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert run["retry_epoch"] == 1 and run["usage"]["agent_runtime"]["regenerations"] == 1
    assert target.port.calls == len(target.port.requests) == 2
    fresh = json.dumps([row.content for row in target.port.requests[1]["messages"]], ensure_ascii=False)
    assert "10月21日我有面试" not in fresh and "不能发布的合成旧草稿" not in fresh
    old = target.repo.get(target.owner, "fact", target.bindings["interview"], include_deleted=True)
    assert old["status"] == "deleted" and not old.get("content")
    assert target.repo.is_revoked(target.owner, "fact", old["id"])
    for row in target.repo.list(target.owner, "runtime_step", include_deleted=True):
        if ":e0:" in row["id"]:
            assert row["status"] == "deleted" and not row.get("output")
    proof = target.case_evidence()
    names = [row["name"] for row in proof["semantic_observations"]]
    assert names.count("context.invalidated") == names.count("run.regenerated") == 1
    assert proof["external_provider_requests"] == 0

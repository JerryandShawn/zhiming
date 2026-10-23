"""Real native layers must be present, cleared and invalidated before privacy evidence counts."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from psycopg import sql

from tools.eval.contracts import scenario_contract_hash
from tools.eval.engine import evaluate_scenario
from tools.eval.schema import Scenario, load_scenarios
from tools.eval.targets.v4_corpus import execution_overlay
from tools.eval.targets.v4_target import V4Target

from .test_eval_v4_pg import target as base_target


@pytest.fixture(name="target")
def privacy_target(monkeypatch: pytest.MonkeyPatch) -> Iterator[V4Target]:
    yield from base_target.__wrapped__(monkeypatch)


def original(ident: str) -> Scenario:
    source = next(c for c in load_scenarios(Path("tools/eval/scenarios")) if c.id == ident)
    case = execution_overlay(source)
    assert scenario_contract_hash(case) == scenario_contract_hash(source)
    return case


@pytest.mark.parametrize("ident", ["F01", "F03"])
def test_declared_layers_are_real_and_no_private_runtime_body_survives(target: V4Target, ident: str) -> None:
    observed = evaluate_scenario(original(ident), target, target_name="v4")
    assert "target_exception" not in observed["failed_assertions"]
    initial = target.privacy_seed.baseline
    assert initial["embedding"] > 0 and initial["search_hit"] > 0
    if ident == "F03":
        assert initial["run_event"] > 0 and initial["run_step"] > 0
    evidence = target.case_evidence()
    assert all(count == 0 for count in evidence["privacy_layers_after"].values())
    frozen_tokens = target.privacy_seed.query_tokens
    assert frozen_tokens and target.privacy_seed.search() == []
    assert target.privacy_seed.query_tokens == frozen_tokens
    for row in target.repo.list(target.owner, "note", include_deleted=True):
        assert row["status"] == "deleted" and "content" not in row
    for run_id in target.privacy_seed.runtime_ids:
        run = target.repo.fetch_run(target.owner, run_id)
        assert run["status"] == "revoked" and run["result"] is None and run["request"] == {}
        with target.repo.transaction(target.owner) as connection:
            assert not connection.execute(
                sql.SQL("SELECT 1 FROM {} WHERE owner=%s AND run_id=%s AND output IS NOT NULL").format(
                    target.repo.table("core_run_steps")
                ),
                (target.owner, run_id),
            ).fetchall()
    # Retain raw native tombstones/statuses; these service invariants do not
    # relabel the unchanged product contract as passed.


def test_late_withdrawal_rebuilds_one_actual_epoch_without_revoked_context(target: V4Target) -> None:
    observed = evaluate_scenario(original("F04"), target, target_name="v4")
    assert observed["status"] == "passed"
    run = target.repo.fetch_run(target.owner, target.run_ids[-1])
    assert run["retry_epoch"] == 1 and run["usage"]["agent_runtime"]["regenerations"] == 1
    withdrawn = target.seeder.ids["interview"]
    assert "fact:" + withdrawn not in run["state_version"]
    snapshot = target.repo.get(target.owner, "runtime_step", f"{run['id']}:e1:agent_initial_context")
    assert withdrawn not in {row["id"] for row in snapshot["output"]["alias_map"].values()}
    replies = [
        row
        for row in target.repo.list(target.owner, "message")
        if row.get("role") == "assistant" and row.get("run_id") == run["id"]
    ]
    assert len(replies) == 1 and withdrawn not in replies[0].get("used_fact_ids", [])
    assert target.port.fired and observed["model_calls"] == 1
